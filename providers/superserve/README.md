# Superserve

Superserve costs are `reported`. The provider's own cost for the sandbox, matching list price.

Superserve's usage API reports each sandbox's compute usage and gross compute cost: a summary total and the charge intervals it sums (a running sandbox's open interval accrues to the read's cutoff). The figure settled at the delete in measured runs and is the reported cost; shared storage is never allocated to a sandbox and is not billed today. Without a record the cost is unknown.

## How the cost is worked out

Superserve's own gross_compute_cost_usd for the sandbox. Check: billed seconds × (vCPUs × CPU rate + GiB of memory × memory rate).

What holds it back: Nothing above the provider's own figure exists. The summary's gross compute cost settled at the delete and equals its own interval records to the last digit.

What would improve it: Nothing. Without a usage record the cost is unknown; list prices are never used to make one.

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
| Per-sandbox data | Yes. GET /billing/usage/summary and /billing/usage/details report one sandbox's compute usage and gross compute cost per billing period through a stated cutoff. The figure settled at the delete on every measured sandbox; shared storage is never allocated and is unbilled. The audit log (GET /activity) still holds the lifecycle times. [^10] |

## Not known yet

- Is storage billed on a pause longer than 12 minutes, or at invoice time? The public pricing data marks it not billable, and a sandbox paused 11 min 18 s with 1 GiB written added no storage charge.
  - To find out: Keep a sandbox paused for hours with a larger diff, compare the team's storage usage and charge with the listed rate, and read the period's invoice.
- Does live memory resizing (memory_current_mib) change the memory billed? The base template is a fixed size, so the idle check could not show it.
  - To find out: Grow a sandbox's memory on a template with memory_max_mib set, let it shrink, and compare the meter with memory_current_mib.
- Is time in pausing, resuming or starting billed? The lifecycle page says active is billed and paused is not, and states no billing for these three. In measured pauses and resumes the meter agreed with the rows (started to paused, resumed to deleted) within 0.4 s.
  - To find out: Pause and resume a sandbox with a large memory image, and compare the team's meter with the time between the call, the row and the status change.
- Are failed and migrating sandboxes billed, and which rows do they write? The lifecycle page says failed means the sandbox could not boot or resume and stays until deleted, and migrating is a temporary move of a paused sandbox. No billing is stated for either, and none was observed.
  - To find out: Read the team's meter and activity rows while a sandbox is failed or migrating. Ask Superserve support how to cause each, and what each bills.
- How long does the audit log keep rows beyond 21 days?
  - To find out: Read the oldest row again after 30, 60 and 90 days.
- Do paused sandboxes, templates and snapshots add a charge beyond storage?
  - To find out: Pause a sandbox for hours and compare the team's usage and charge before and after.

## Our measurements

- 2026-11-22: [The per-sandbox usage API](evidence/2026-11-22-usage-api.md). Four sandboxes (short run, pause/resume, running across polls, made from a snapshot) each got a summary total and interval records in Superserve's own figure; totals settled at the delete and matched the intervals to the last digit. One team, one region, the base template.
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
[^10]: [2026-11-22-usage-api.md](evidence/2026-11-22-usage-api.md#verdict)
