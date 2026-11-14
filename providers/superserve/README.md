# Superserve

Superserve costs are `calculated`. The provider's own usage records priced at list rates.

Superserve reports no cost. Each running period lasts from a started or resumed row of its audit log to the first row that ends it, and is priced at the list rates per second. A sandbox that ends by its own timeout has no deleted row, so its end is the timeout_paused row, or the idle_paused row after an idle timeout. Without an end row the cost is unknown. The cost is calculated, not Superserve's own figure.

## How the cost is worked out

For each running period, from a started or resumed row to the first deleted, paused, idle_paused, timeout_paused or auto_deleted row: seconds × (vCPUs × CPU rate + GiB of memory × memory rate). With no end row the cost is unknown.

What holds it back: Superserve reports no per-sandbox cost or billed usage, only audit-log lifecycle rows, which are priced at list rates.

What would improve it: A per-sandbox cost or billed usage from Superserve that matches the list-price calculation on measured sandboxes.

## Rates

From [`superserve@2026-11-13-141358Z`](../../src/sandbox_provider_pricing/providers/superserve/prices/2026-11-13-141358Z.yaml), in effect from 2026-06-17, default class `default`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| CPU | $0.000014 per vCPU-second | size requested | running |
| Memory | $0.0000045 per GiB-second | size requested | running |

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | $0.000014 per vCPU-second and $0.0000045 per GiB-second of the memory the sandbox holds, while it runs. Storage on retained data is a separate resource that Superserve tracks but does not bill: a sandbox paused 11 min 18 s with 1 GiB written added no storage charge. [^1][^2][^3][^4][^5] |
| Billing starts | Not stated. The calculator uses the started row (or resumed after a pause), which fell inside the create call on six sandboxes. The team's usage meter ran 0.09 to 0.38 s less than the rows on every period, so the rows are an upper bound. [^6] |
| Billing ends | Compute and memory stop when the sandbox is paused. The calculator ends at the first deleted, paused, idle_paused, timeout_paused or auto_deleted row; the deleted row fell inside the destroy call on four sandboxes. The meter stopped before the idle_paused row (by 1.05 s) and before the timeout_paused row, which auto_deleted followed 0.24 s later. [^1][^7][^8] |
| Rounding | Billed per second; no minimum or rounding increment is stated. The usage meter reports microsecond fractions. [^1][^4] |
| Idle and paused | An idle running sandbox bills its full compute and memory: one left idle 8 min stayed active at full size. Superserve pauses a sandbox only on a timeout it is given (idle_timeout_seconds, timeout_seconds), an explicit pause or a delete; both timeouts are unset by default. A paused sandbox bills nothing: the meter stayed flat for 43 s of idle pause. [^1][^3][^7][^8][^9] |
| Image pull | Not stated; not yet measured. To find out: Compare billed usage for a first create from a large template with a later create from the same template. |
| Billed separately | Storage on a shared template and retained sandbox changes is listed per GiB-hour but marked not billable, and a sandbox paused 11 min 18 s was charged 0 for it. The pricing page says its estimates exclude network and external model API charges; no network charge is published. [^1][^2][^5] |
| Left out | Storage, plan fees, the included usage on paid plans, taxes, network and external model API charges. [^1] |
| Per-sandbox data | No cost or usage. The audit log (GET /activity) has a started, paused, resumed, idle_paused, timeout_paused, deleted or auto_deleted row for each lifecycle change, with no size or cost. The first read returned each row within 0.771 s, and rows were readable at 21 days. Without a limit it returns only the newest 200 rows. [^10][^11] |

## Not known yet

- Is storage billed on a pause longer than 12 minutes, or at invoice time? The public pricing data marks it not billable, and a sandbox paused 11 min 18 s with 1 GiB written added no storage charge.
  - To find out: Keep a sandbox paused for hours with a larger diff, compare the team's storage usage and charge with the listed rate, and read the period's invoice.
- Does the meter start before the started row, and end before the ending row? The rows ran 0.09 to 0.38 s longer than the meter.
  - To find out: Compare the meter of many short sandboxes with their rows, and look for a fixed offset at each end.
- Does live memory resizing (memory_current_mib) change the memory billed? The base template is a fixed size, so the idle check could not show it.
  - To find out: Grow a sandbox's memory on a template with memory_max_mib set, let it shrink, and compare the meter with memory_current_mib.
- Is time in pausing, resuming or starting billed? The lifecycle page says active is billed and paused is not, and states no billing for these three. In measured pauses and resumes the meter agreed with the rows (started to paused, resumed to deleted) within 0.4 s.
  - To find out: Pause and resume a sandbox with a large memory image, and compare the team's meter with the time between the call, the row and the status change.
- Are failed and migrating sandboxes billed, and which rows do they write? The lifecycle page says failed means the sandbox could not boot or resume and stays until deleted, and migrating is a temporary move of a paused sandbox. No billing is stated for either, and none was observed.
  - To find out: Read the team's meter and activity rows while a sandbox is failed or migrating. Ask Superserve support how to cause each, and what each bills.
- Does an account rate differ from the list rate?
  - To find out: Compare a negotiated account's meter delta with the list rates for one sandbox.
- How long does the audit log keep rows beyond 21 days?
  - To find out: Read the oldest row again after 30, 60 and 90 days.
- Do paused sandboxes, templates and snapshots add a charge beyond storage?
  - To find out: Pause a sandbox for hours and compare the team's usage and charge before and after.

## Our measurements

- 2026-11-14: [Idle time on a sandbox](evidence/2026-11-14-idle-and-idle-timeout.md). A sandbox with no idle timeout, idle 8 min 14 s, stayed active and billed 2 vCPU and 4,096 MiB throughout. One with idle_timeout_seconds 60 was paused about 67 s after its last command, and the meter stopped there for the 43 s read. One team, one region, the base template.
- 2026-11-13: [Storage on a paused sandbox](evidence/2026-11-13-paused-storage.md). One sandbox with 1 GiB of random data written, paused 11 min 18 s, added no storage charge. Storage usage was tracked in the team's hourly series (2,414.76 GiB-seconds, billable false, cost 0). One team, one region, one pause.
- 2026-11-13: [Billing boundary against Superserve lifecycle rows](evidence/2026-11-13-billing-boundary.md). On six sandboxes rows priced at list rates came to 0.4% above the team's billing meter, including a 2048 MiB sandbox, a pause and resume, and a timeout. One team, one region, 30 to 90 s.

## Price versions

- [`superserve@2026-11-13-141358Z`](../../src/sandbox_provider_pricing/providers/superserve/prices/2026-11-13-141358Z.yaml): from 2026-06-17, read 2026-11-13, in effect now.
- [`superserve@2026-11-13`](../../src/sandbox_provider_pricing/providers/superserve/prices/2026-11-13.yaml): from 2026-06-17, read 2026-11-13, replaced by `superserve@2026-11-13-141358Z`.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/superserve/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [superserve.ai/pricing](https://www.superserve.ai/pricing/)
[^2]: [api.superserve.ai/billing/pricing/public](https://api.superserve.ai/billing/pricing/public)
[^3]: [docs.superserve.ai/sandbox/live-memory-resizing](https://docs.superserve.ai/sandbox/live-memory-resizing)
[^4]: [2026-11-13-billing-boundary.md](evidence/2026-11-13-billing-boundary.md#audit-log-rows-and-billed-seconds-per-sandbox)
[^5]: [2026-11-13-paused-storage.md](evidence/2026-11-13-paused-storage.md#verdict)
[^6]: [2026-11-13-billing-boundary.md](evidence/2026-11-13-billing-boundary.md#verdict)
[^7]: [docs.superserve.ai/sandbox/lifecycle](https://docs.superserve.ai/sandbox/lifecycle)
[^8]: [2026-11-13-billing-boundary.md](evidence/2026-11-13-billing-boundary.md#what-ended-each-sandbox)
[^9]: [2026-11-14-idle-and-idle-timeout.md](evidence/2026-11-14-idle-and-idle-timeout.md#verdict)
[^10]: [2026-11-13-billing-boundary.md](evidence/2026-11-13-billing-boundary.md#event-lag-separate-from-billing)
[^11]: [2026-11-13-billing-boundary.md](evidence/2026-11-13-billing-boundary.md#retention)
