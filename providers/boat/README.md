# Boat

Boat costs are `reported`. The provider's own cost for the sandbox, matching list price.

Boat reports a per-sandbox cost: GET /sandboxes/{id}/usage returns billable machine-seconds weighted by size (small 0.5, default 1, large 2, xlarge 50/9) and dollars at list price. The meter runs only while the sandbox runs. A stopped sandbox keeps its disk free for at least 14 days before it becomes eligible for retention cleanup. The list price is a flat per-hour rate per size with no published per-unit split, carried in the price version as a per-size machine rate.

## How the cost is worked out

The sandbox's usage record, read with the meter stopped (running: false) or last read before Boat deleted the sandbox and its record (as of that read): its dollars at list price. No record, another sandbox's, or a moving meter with no known end is unknown.

What holds it back: Nothing. The figure counts when the usage record names this sandbox and running is false, or is the last read before Boat deleted the record; that read can fall short by the seconds before the delete.

What would improve it: Nothing. A missing usage record, a record that names another sandbox, or a read of a sandbox with no known end whose meter still moves leaves the cost unknown.

## Rates

From [`boat@2026-11-01-052001Z`](../../src/sandbox_provider_pricing/providers/boat/prices/2026-11-01-052001Z.yaml), in effect from 2026-11-01, default class `default`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| Machine (small) | $0.018 per machine-hour | size requested | running |
| Machine (default) | $0.036 per machine-hour | size requested | running |
| Machine (large) | $0.072 per machine-hour | size requested | running |
| Machine (xlarge) | $0.200 per machine-hour | size requested | running |
| Disk | $0 per GiB-hour | size requested | stopped |

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | Billable machine-seconds, weighted by size multiplier (0.5, 1, 2, 50/9 for small, default, large, xlarge), at $0.036 per hour of default size (secondsPerDollar 100000), while the sandbox runs. Published as a flat per-hour rate per size: small $0.018, default $0.036, large $0.072, xlarge $0.200. No size has a GPU. [^1][^2] |
| Billing starts | Not stated where the meter starts inside a create, resume or fork call. The usage record's seconds is the billed quantity, so the edge is Boat's own meter, not a call boundary. [^2][^3] |
| Billing ends | A stop ends machine billing: stopped time is never counted, and time past a refused stop is excluded. Auto-stop ends a sandbox after its deadline (1 hour by default). [^2][^3] |
| Rounding | Billed per second. The usage API returns whole billable machine-seconds and dollars to six decimals; no minimum duration or rounding increment is published. [^1][^2] |
| Idle and paused | There is no pause; an idle sandbox bills as running until it stops or auto-stops. A stopped sandbox costs no machine time and keeps its disk free for at least 14 days. After that it is eligible for automated retention cleanup. The provider currently documents the production cleanup job as reporting candidates without deleting them. [^1][^3] |
| Image pull | Not stated; environment or image load time is not broken out on the billing pages. To find out: Compare billable seconds for a sandbox created from a cold environment against a cached one at known durations. |
| Billed separately | Extra starts cost $0.03 to $0.07 each. Create, fork and resume count. The wallet pays first. An opted-in invoice can pay when the wallet is empty. Extra saved snapshots cost $0.056 each per day. The AI proxy costs $1 per enabled day plus $1 per 1,000 requests. Snapshot and proxy charges draw from the wallet. Egress is free. [^1][^3][^4] |
| Left out | Plan commitments ($20/$100/$500/$2000 per month per seat, returned as VM time at list rates), included starts and concurrency limits, the wallet bonus of 2% to 25% on payments of $200 or more, the 7-day free trial's limits, the $100-plan requirement for xlarge, and taxes. [^1][^3] |
| Per-sandbox data | GET /sandboxes/{id}/usage reports weighted seconds, list-priced dollars, running state and the size. After deletion the sandbox's usage record is unavailable. The last pre-delete read may omit time before deletion. List include=cost returns an aggregate deletedCost, without a per-sandbox breakdown. [^2][^3] |

## Not known yet

- For how long does the list include=cost deletedCost aggregate keep a deleted sandbox, and is that line attributable per sandbox?
  - To find out: After delete, re-read the list include=cost deletedCost line at intervals and compare it with the last per-sandbox usage read.
- Can dollars be corrected after running turns false?
  - To find out: Re-read a stopped sandbox's usage over days and compare figures; check whether the dashboard's month cost ever revises a closed sandbox.
- Is the reported dollars figure exactly the published per-hour size rate on real sandboxes?
  - To find out: Compare usage.dollars against seconds times the stored rate on several sizes; the docs state the identity but no billed record has been checked.
- Are starts (paid $0.03 to $0.07 above the included count) attributable to a sandbox or start event?
  - To find out: Exceed included starts on a funded account and look for a per-start or per-sandbox charge record.
- Is image pull or restore time billed?
  - To find out: Compare billable seconds for a cold environment against a cached one at known durations.
- Does the usage record survive a refused stop, and does resume with a new size change the multiplier mid-life?
  - To find out: Refuse a stop, resume on a different size, and read the record's sandboxType and seconds across the change.

## Our measurements

None yet.

## Price versions

- [`boat@2026-11-01-052001Z`](../../src/sandbox_provider_pricing/providers/boat/prices/2026-11-01-052001Z.yaml): from 2026-11-01, read 2026-11-01, in effect now.
- [`boat@2026-11-01`](../../src/sandbox_provider_pricing/providers/boat/prices/2026-11-01.yaml): from 2026-11-01, read 2026-11-01, replaced by `boat@2026-11-01-052001Z`.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/boat/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [docs.boat.dev/pricing](https://docs.boat.dev/pricing)
[^2]: [docs.boat.dev/api/reference/sandboxes/get-sandbox-usage](https://docs.boat.dev/api/reference/sandboxes/get-sandbox-usage)
[^3]: [docs.boat.dev/billing](https://docs.boat.dev/billing)
[^4]: [docs.boat.dev/limits](https://docs.boat.dev/limits)
