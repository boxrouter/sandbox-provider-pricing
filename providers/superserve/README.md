# Superserve

Superserve costs are `unknown`. No provider evidence gives a figure, so there is no cost. The total is `null`.

Superserve bills compute and memory per second at the same list rates on every plan, only while a sandbox runs. Storage is listed at a rate by one source and marked not billable by another, so it is left out and the cost stays unknown. Billing boundaries and per-sandbox records are not measured.

## How the cost is worked out

Unknown until the billing boundaries are measured. List-rate estimate for a running period: seconds × (vCPUs × CPU rate + GiB of memory × memory rate), plus storage if it is billed.

What holds it back: Superserve documents no per-sandbox usage or cost record and no lifecycle event feed, and its billing boundaries have not been measured.

What would improve it: A per-sandbox usage record, or measured start and end boundaries that let lifecycle times be priced at the list rates.

## Rates

From [`superserve@2026-11-13`](../../src/sandbox_provider_pricing/providers/superserve/prices/2026-11-13.yaml), in effect from 2026-06-17, default class `default`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| CPU | $0.000014 per vCPU-second | size requested | running |
| Memory | $0.0000045 per GiB-second | size requested | running |

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | $0.000014 per vCPU-second and $0.0000045 per GiB-second of the memory the sandbox holds, while it runs. Storage on retained data is a separate meter whose billing the sources contradict. [^1][^2][^3] |
| Billing starts | Not stated; not yet measured. To find out: Compare billed usage with a sandbox's create and ready times on an account whose usage can be read. |
| Billing ends | Compute and memory stop billing when the sandbox is paused. Not stated for delete or for time spent pausing. [^1][^4] |
| Rounding | Billed per second; no minimum or rounding increment is stated. [^1] |
| Idle and paused | A running sandbox bills compute and memory whether or not it is busy. A paused sandbox bills neither; its retained data is the storage meter. [^1][^3][^4] |
| Image pull | Not stated; not yet measured. To find out: Compare billed usage for a first create from a large template with a later create from the same template. |
| Billed separately | Storage on a shared template and retained sandbox changes, if billed. The pricing page says its estimates exclude network and external model API charges; no network charge is published. [^1] |
| Left out | Storage, plan fees, the included usage on paid plans, taxes, network and external model API charges. [^1] |
| Per-sandbox data | Unknown. A team-level usage endpoint is described, but no per-sandbox usage or cost record is documented. To find out: Read a team's usage after running one sandbox alone and compare it with the sandbox's own record. |

## Not known yet

- Is storage billed? The pricing page lists it at a per GiB-hour rate while retained, and the public pricing data marks it not billable.
  - To find out: Ask Superserve, or compare a team's reported storage usage and charge for retained sandboxes against the listed rate.
- Do paused sandboxes, templates and snapshots add a charge beyond storage?
  - To find out: Pause a sandbox for a measured period and compare a team's usage before and after.
- Are time spent starting, pausing and resuming billed?
  - To find out: Compare billed usage with the timestamps of one sandbox's lifecycle transitions.

## Our measurements

None yet.

## Price versions

- [`superserve@2026-11-13`](../../src/sandbox_provider_pricing/providers/superserve/prices/2026-11-13.yaml): from 2026-06-17, read 2026-11-13, in effect now.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/superserve/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [superserve.ai/pricing](https://www.superserve.ai/pricing/)
[^2]: [api.superserve.ai/billing/pricing/public](https://api.superserve.ai/billing/pricing/public)
[^3]: [docs.superserve.ai/sandbox/live-memory-resizing](https://docs.superserve.ai/sandbox/live-memory-resizing)
[^4]: [docs.superserve.ai/sandbox/lifecycle](https://docs.superserve.ai/sandbox/lifecycle)
