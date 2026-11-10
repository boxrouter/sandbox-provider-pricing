# Reservation quotes

`reservation_quote()` answers "what is the most this size can cost if it runs for this long?" Use
it to reserve funds or set a budget before a sandbox exists. It reads only a price version, never a
sandbox's records, so its answer is not a sandbox cost and carries no cost label.

```python
from sandbox_provider_pricing import reservation_quote
from sandbox_provider_pricing.versions import latest_version

quote = reservation_quote(
    latest_version("vercel"),  # or the price version you stored
    {"cpu": 2, "memory_mib": 4096},
    3600,  # seconds
    region=None,
    class_name=None,
    creation=True,
)
print(quote["status"], quote["ceiling_usd"])  # bounded 0.3408006
```

The quote prices one continuous run plus, with `creation=True`, the creation fee. It applies each
meter's minimum and increment and the region multiplier, and it assumes full use of every meter
billed only while in use. Network egress and retained storage are not included.

Whether anything billable is missing from the quote is the price version's `coverage`: one entry
per charge kind (`cpu`, `memory`, `disk`, `creation`, `egress`, `snapshot_storage`,
`image_storage`, `volume_storage`, `requests`), each with a source and one treatment:

| Treatment | Meaning |
| --- | --- |
| `in_quote` | Priced into the quote: running time, or the one creation fee. |
| `not_billed` | The provider does not bill it on managed sandboxes. |
| `unbounded` | Billable, or not published and so not assumed free, but a size and a duration give no ceiling (egress, retained storage, requests, use-based charges). The quote leaves it out and lists it in `excluded`. |

The quote is `bounded` only when every kind is stated and cpu, memory and disk are not `unbounded`.
A kind left out, a version with no `coverage`, or an entry that contradicts the rate card (a
`not_billed` charge the class prices, an `in_quote` egress) makes the quote `unknown`.

| Field | What it holds |
| --- | --- |
| `kind` | Always `reservation_quote`. |
| `status` | `bounded`, `unbounded` or `unknown`. |
| `ceiling_usd` | The ceiling as a decimal string, or `null` unless `status` is `bounded`. |
| `price_version` | The price version quoted. |
| `held_back_by` | Why there is no ceiling, one sentence per meter. |
| `excluded` | What the price version leaves out, plus egress and retained storage and each `unbounded` charge with its note. |

A meter billed on the larger of request and use cannot be bounded from the request, so Modal
returns `unbounded`, as does an `unbounded` cpu, memory or disk coverage entry. A missing size,
rate, class or coverage entry returns `unknown`, and that wins over `unbounded`.

For an hourly rate-card figure that may be a range, use `per_hour` or `hourly` instead
([calculator](calculator.md)).

## Prospective lifecycle quote

`lifecycle_quote()` prices the demand supplied for each running, paused or stopped period. The
result is conditional on those values. It is not an expected task charge, a reservation ceiling or
the actual cost of a sandbox. It reads no provider records and creates no evidence.

```python
from sandbox_provider_pricing import LifecyclePeriod, lifecycle_quote
from sandbox_provider_pricing.versions import latest_version

quote = lifecycle_quote(
    latest_version("e2b"),
    {"cpu": 2, "memory_mib": 4096},
    (
        LifecyclePeriod("running", 600),
        LifecyclePeriod("paused", 1200),
    ),
    egress_bytes=0,  # total egress across this lifecycle
)
print(quote["status"], quote["amount_usd"])  # known 0.0276
```

Each billed period keeps its own minimum and increment. On each `LifecyclePeriod`,
`active_cpu_seconds` is total CPU use for that period and `snapshot_bytes` is its snapshot size.
Pass `creations` and `egress_bytes` to `lifecycle_quote`; both apply to the whole lifecycle. Only a
CPU meter priced by active demand needs `active_cpu_seconds`; an allocated CPU meter uses the
supplied size and period duration. Supply snapshot bytes for every positive period in a state that
bills snapshot storage. If a required demand value is missing, the quote is `unknown` with a null
amount.
