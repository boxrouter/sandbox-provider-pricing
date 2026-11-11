# sandbox-provider-pricing

List prices for sandbox providers, and a calculator that turns a provider's own records for one
sandbox into a cost.

A cost has one of two labels:

- `reported`: the provider's own figure for the sandbox, checked against its list prices.
- `calculated`: the provider's own usage or lifecycle records, priced at its list rates.

Otherwise there is no cost. The result says `unknown` with a `null` total, never zero or a guess,
and consumers show nothing. Our own clocks never stand in for the provider's.

[METHOD.md](METHOD.md) defines these and says what a cost includes.

## Providers

<!-- generated:provider-status -->
| Provider | Best cost available | How it is worked out |
| --- | --- | --- |
| [Agent37](providers/agent37/README.md) | `reported` | Agent37's compute_micros for the instance, divided by one million. Check: billed minutes × (vCPUs × CPU rate + GB of RAM × memory rate) ÷ 43,800 for running minutes, plus GB of disk × disk rate ÷ 43,800 for every minute. |
| [Blaxel](providers/blaxel/README.md) | `reported` | Blaxel's own cost for the sandbox. Check: active seconds × GB of memory × memory rate (CPU is included), plus snapshot GB × seconds in standby × snapshot rate. |
| [Boat](providers/boat/README.md) | `reported` | The sandbox's usage record, read with the meter stopped (running: false) or last read before Boat deleted the sandbox and its record (as of that read): its dollars at list price. No record, another sandbox's, or a moving meter with no known end is unknown. |
| [boxd](providers/boxd/README.md) | `reported` | A complete USD machines.usage(id) record for this machine, with rates matching the stored list version, reports cost_micro divided by one million. Otherwise unknown; no calculated fallback. |
| [Daytona](providers/daytona/README.md) | `reported` | Daytona's own price for the sandbox. Check: billed seconds × (vCPUs × CPU rate + GiB of memory × memory rate + GiB of disk × disk rate). |
| [E2B](providers/e2b/README.md) | `calculated` | For each running period, from a created or resumed event to the next paused or killed event: seconds × (vCPUs × CPU rate + GiB of memory × memory rate). |
| [Modal](providers/modal/README.md) | `reported` | Modal's own bill for the App, when it held only this sandbox: the sum of hourly USD rows and covered empty hours, read at least 600 seconds after finished_at. An image preparation is priced the same way from its own stopped App. Otherwise unknown. |
| [Vercel](providers/vercel/README.md) | `calculated` | GB of memory × run time in whole minutes × memory rate + active CPU hours × CPU rate + creations × creation fee + GB sent × egress rate + snapshot GB-months × storage rate. |
<!-- /generated:provider-status -->

Each provider page lists its rates, its billing rules with sources, and what is still unknown.
[COMPARING.md](COMPARING.md) explains why the same rate can mean different costs on different
providers.

## Install

The package needs Python 3.11 to 3.14 and has two dependencies, `jsonschema` and `pyyaml`. From a
checkout of this repository, with [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked --no-dev
```

Each release is published to PyPI as
[`sandbox-provider-pricing`](https://pypi.org/project/sandbox-provider-pricing/).

## Price one sandbox

This prices a recorded Vercel sandbox: 2 vCPUs and 4 GiB, running for two minutes with 11 seconds
of busy CPU. Run it with `uv run python` from the repository root.

```python
import json
from decimal import Decimal
from pathlib import Path

from sandbox_provider_pricing import price

evidence = json.loads(Path("providers/vercel/fixtures/best/evidence.json").read_text())
result = price(evidence)

print(result["label"], f"{Decimal(result['total']['low']):.6f} USD")
for line in result["lines"]:
    print(" ", line["what"], line["rate"], "per", line["unit"], f"{Decimal(line['amount']):.6f}")
print("final:", result["final"], "| next read:", result["revisit"]["next_read_at"])
```

The evidence is what you collected about the sandbox: what you asked for and the provider's own
records. [Using `price()`](docs/using-price.md) shows how to build it from provider usage reports.

## Reading a result

| Field | What it holds |
| --- | --- |
| `label` | `reported`, `calculated` or `unknown`. |
| `total` | `{"low": ..., "high": ...}` in USD as decimal strings, low equal to high, or `null` when unknown. |
| `lines` | One line per meter: quantity, unit, rate and amount. Empty when unknown. |
| `held_back_by` | Why the cost is not better: a code and a sentence for each missing record or rate. |
| `final` | `true` once the retry window has closed and the result will not be read again. |
| `revisit` | When to read the provider's records again, with `next_read_at`; `null` once final. |
| `steps` | The evidence, the derived usage and the rated documents, so anyone can reproduce the result. |

Store the whole result. `reproduce(result)` re-rates its usage with the price version it records.

## More

| Topic | Where |
| --- | --- |
| Building evidence and reading late provider reports | [docs/using-price.md](docs/using-price.md) |
| Combining several resources into one total | [docs/compose.md](docs/compose.md) |
| A spending ceiling for a size and duration | [docs/reservation-quote.md](docs/reservation-quote.md) |
| The low-level calculator and hourly quotes | [docs/calculator.md](docs/calculator.md) |
| The price sheet for price displays | [docs/price-sheet.md](docs/price-sheet.md) |
| The cost method and a cost's working as data | [docs/cost-method.md](docs/cost-method.md) |
| JSON Schemas and bundled price versions | [docs/formats.md](docs/formats.md) |
| Checking that published prices have not changed | [docs/watching-prices.md](docs/watching-prices.md) |
| How costs are worked out | [METHOD.md](METHOD.md) |
| Adding or reviewing a provider | [docs/adding-a-provider.md](docs/adding-a-provider.md) |
| Changes and releases | [CHANGELOG.md](CHANGELOG.md), [RELEASE.md](RELEASE.md) |

## Contributing

Corrections from providers and users are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md).
BoxRouter maintains this repository and routes paid sandbox traffic to these providers; its own
prices and margins are not here. [Governance](.github/GOVERNANCE.md) says how changes are decided.
Report vulnerabilities as [SECURITY.md](SECURITY.md) describes. The code and data are under the
[Apache-2.0 license](LICENSE).
