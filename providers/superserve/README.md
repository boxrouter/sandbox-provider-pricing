# Superserve

Superserve costs are `calculated`. The provider's own usage records priced at list rates.

Superserve reports no cost. Each running period lasts from a started or resumed row of its audit log to the first row that ends it, and is priced at the list rates per second. A sandbox that ends by its own timeout has no deleted row, so its end is the timeout_paused row. Without an end row the cost is unknown. The cost is calculated, not Superserve's own figure.

## How the cost is worked out

For each running period, from a started or resumed row to the first deleted, paused, timeout_paused or auto_deleted row: seconds × (vCPUs × CPU rate + GiB of memory × memory rate). With no end row the cost is unknown.

What holds it back: Superserve reports no per-sandbox cost or billed usage, only audit-log lifecycle rows, which are priced at list rates.

What would improve it: A per-sandbox cost or billed usage from Superserve that matches the list-price calculation on measured sandboxes.

## Rates

From [`superserve@2026-11-13`](../../src/sandbox_provider_pricing/providers/superserve/prices/2026-11-13.yaml), in effect from 2026-06-17, default class `default`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| CPU | $0.000014 per vCPU-second | size requested | running |
| Memory | $0.0000045 per GiB-second | size requested | running |

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | $0.000014 per vCPU-second and $0.0000045 per GiB-second of the memory the sandbox holds, while it runs. Storage on retained data is a separate meter whose billing the sources contradict; its usage stayed 0 in every measured sandbox. [^1][^2][^3][^4] |
| Billing starts | Not stated. The calculator uses the started row (or resumed after a pause), which fell inside the create call on six sandboxes. The team's usage meter ran 0.09 to 0.38 s less than the rows on every period, so the rows are an upper bound. [^5] |
| Billing ends | Compute and memory stop when the sandbox is paused. The calculator ends at the first deleted, paused, timeout_paused or auto_deleted row; the deleted row fell inside the destroy call on four sandboxes. A sandbox that ends by its own timeout has no deleted row: the meter stopped before its timeout_paused row, and auto_deleted followed 0.24 s later. [^1][^6][^7] |
| Rounding | Billed per second; no minimum or rounding increment is stated. The usage meter reports microsecond fractions. [^1][^4] |
| Idle and paused | A running sandbox bills compute and memory whether or not it is busy. A paused sandbox bills neither: a 30.956 s pause between paused and resumed rows added nothing to the meter, and a sandbox deleted 7.64 s after pausing billed only its running time. [^1][^3][^6][^7] |
| Image pull | Not stated; not yet measured. To find out: Compare billed usage for a first create from a large template with a later create from the same template. |
| Billed separately | Storage on a shared template and retained sandbox changes, if billed. The pricing page says its estimates exclude network and external model API charges; no network charge is published. [^1] |
| Left out | Storage, plan fees, the included usage on paid plans, taxes, network and external model API charges. [^1] |
| Per-sandbox data | No cost or usage. The audit log (GET /activity) has a started, paused, resumed, timeout_paused, deleted or auto_deleted row for each lifecycle change, with no size or cost. The first read returned each row within 0.771 s, and rows were readable at 21 days. Without a limit it returns only the newest 200 rows. [^8][^9] |

## Not known yet

- Is storage billed? The pricing page lists it at a per GiB-hour rate while retained, and the public pricing data marks it not billable. The team's storage usage stayed 0 over six sandboxes of 30 to 90 s.
  - To find out: Keep a sandbox paused for hours, and compare the team's storage usage and charge with the listed rate.
- Does the meter start before the started row, and end before the ending row? The rows ran 0.09 to 0.38 s longer than the meter.
  - To find out: Compare the meter of many short sandboxes with their rows, and look for a fixed offset at each end.
- Does live memory resizing (memory_current_mib) change the memory billed?
  - To find out: Grow a sandbox's memory during a measured run and compare the meter with the allocated size.
- Which rows do idle-timeout pauses, failed creates and migrations write, and are they billed?
  - To find out: Trigger each state on one sandbox and compare its rows with the team's meter.
- Does an account rate differ from the list rate?
  - To find out: Compare a negotiated account's meter delta with the list rates for one sandbox.
- How long does the audit log keep rows beyond 21 days?
  - To find out: Read the oldest row again after 30, 60 and 90 days.
- Do paused sandboxes, templates and snapshots add a charge beyond storage?
  - To find out: Pause a sandbox for hours and compare the team's usage and charge before and after.

## Our measurements

- 2026-11-13: [Billing boundary against Superserve lifecycle rows](evidence/2026-11-13-billing-boundary.md). On six sandboxes rows priced at list rates came to 0.4% above the team's billing meter, including a 2048 MiB sandbox, a pause and resume, and a timeout. One team, one region, 30 to 90 s.

## Price versions

- [`superserve@2026-11-13`](../../src/sandbox_provider_pricing/providers/superserve/prices/2026-11-13.yaml): from 2026-06-17, read 2026-11-13, in effect now.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/superserve/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [superserve.ai/pricing](https://www.superserve.ai/pricing/)
[^2]: [api.superserve.ai/billing/pricing/public](https://api.superserve.ai/billing/pricing/public)
[^3]: [docs.superserve.ai/sandbox/live-memory-resizing](https://docs.superserve.ai/sandbox/live-memory-resizing)
[^4]: [2026-11-13-billing-boundary.md](evidence/2026-11-13-billing-boundary.md#audit-log-rows-and-billed-seconds-per-sandbox)
[^5]: [2026-11-13-billing-boundary.md](evidence/2026-11-13-billing-boundary.md#verdict)
[^6]: [docs.superserve.ai/sandbox/lifecycle](https://docs.superserve.ai/sandbox/lifecycle)
[^7]: [2026-11-13-billing-boundary.md](evidence/2026-11-13-billing-boundary.md#what-ended-each-sandbox)
[^8]: [2026-11-13-billing-boundary.md](evidence/2026-11-13-billing-boundary.md#event-lag-separate-from-billing)
[^9]: [2026-11-13-billing-boundary.md](evidence/2026-11-13-billing-boundary.md#retention)
