# Contributing

Corrections are welcome from anyone, and providers are welcome to review and correct their own
pages. Read the [README](README.md) and [METHOD.md](METHOD.md) first. [Governance](.github/GOVERNANCE.md)
says how changes are decided.

## Setting up

You need [uv](https://docs.astral.sh/uv/):

```sh
uv sync --locked
make check
```

`make check` runs formatting, lint, types and the tests, all offline. Run `make lint` and the tests
you changed (`uv run pytest tests/test_prices.py`) while you work; CI runs `make check` on main.
Checking price pages and drafting a price version reach the network and are not part of it.

## Correcting a price or a billing rule

Open an issue with the price correction form, or a pull request. A correction brings one of:

- a public source: the provider's page, with a verbatim quote of the figure;
- a measurement committed under `providers/<provider>/evidence/` with its date, sample size and
  method, so anyone can repeat it.

Where the provider documents nothing, the answer is `not stated by the provider` or `unknown`,
with the check that would settle it. Never guess a value.

A published price version never changes. A correction is a new price version whose `supersedes`
names the version it replaces, listing only versions still in the checkout.
[Adding a provider](docs/adding-a-provider.md) has the steps and the checks a new version must
pass.

## Adding a provider

Follow [docs/adding-a-provider.md](docs/adding-a-provider.md).

## Generated files

Do not edit these by hand. Change their source and regenerate:

| File | Source | Command |
| --- | --- | --- |
| `providers/<name>/README.md`, the tables in README.md and COMPARING.md | `billing.yaml`, price versions | `make docs` |
| `providers/<name>/fixtures/<case>/result.json` | `evidence.json` beside it | `make update-fixtures` |
| `tests/fixtures/price-sheet.json` | `build_price_sheet()`, with the release version blanked | `make update-fixtures` |
| `tests/released-digests.txt` | price files in the latest release | `make release-digests`, in the release commit ([RELEASE.md](RELEASE.md)) |

The tests fail, naming the command, when one of these is out of date.

## Style

Write for a reader who has never seen this repository. Use short, plain sentences, give the unit
and the basis with every figure, and state each rule once, linking to it elsewhere. Name a product
only to identify it.

Never commit a key, an account id or a local path.

## Reporting a vulnerability

Do not open a public issue: follow [SECURITY.md](SECURITY.md).
