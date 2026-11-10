# Vercel

Vercel costs are `calculated`. The provider's own usage records priced at list rates.

Vercel's session records give each session's duration, active CPU time and bytes sent, and its snapshot records give each snapshot's sizeBytes. Memory is priced in whole minutes, and CPU, creations, egress and snapshot storage at list rates. A missing record leaves the cost unknown.

## How the cost is worked out

GB of memory × run time in whole minutes × memory rate + active CPU hours × CPU rate + creations × creation fee + GB sent × egress rate + snapshot GB-months × storage rate.

What holds it back: Vercel reports usage per session but no cost per sandbox, and the memory billing boundary is unchecked.

What would improve it: A check that billed memory and snapshot storage in the charges API match session times and snapshot sizeBytes.

## Rates

From [`vercel@2026-10-20-055631Z`](../../src/sandbox_provider_pricing/providers/vercel/prices/2026-10-20-055631Z.yaml), in effect from 2026-09-29, default class `default`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| CPU | $0.128 per vCPU-hour | only while in use | running |
| Memory | $0.0212 per GB-hour | size requested, in 60 s increments | running |
| Creation | $0.60 per million-creations |  |  |
| Network egress | $0.15 per GB |  |  |
| Snapshot storage | $0.08 per GB-month |  | stopped |

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | Memory as provisioned (2 GB per vCPU), CPU as active use (I/O wait is not counted). Whether Active CPU is per vCPU or per sandbox, and whether GB is 1,000 or 1,024 MB, is not stated. [^1][^2] |
| Billing starts | Not stated. In five samples the session startedAt fell inside our create call; no bill was compared. [^1][^3] |
| Billing ends | Not stated. In five samples stoppedAt came before our destroy call and duration equalled stoppedAt minus startedAt; no bill was compared. [^1][^3] |
| Rounding | Provisioned memory is billed in 1-minute minimum increments. No rule is published for Active CPU. Creations are counted per call. [^1] |
| Idle and paused | Not stated for starting, stopping or stopped sessions. A stopped persistent sandbox keeps a snapshot, billed as snapshot storage; deleting the sandbox does not delete it. [^1][^4][^5] |
| Image pull | Not stated. Creation waits until the sandbox is ready, and restoring an uncached snapshot is included in creation time. We did not test cold against cached images. [^5][^6] |
| Billed separately | Creation $0.60 per million. Network: data sent out and all exposed-port traffic, $0.15 per GB in iad1. Snapshots $0.08 per GB-month. Disk (64 GB) is included. Not stated: GPU. [^1][^7][^8] |
| Left out | Plan fees and allowances, other regions than iad1, enterprise pricing, taxes, Drives, container registry storage and the snapshot kept after the last stop (30 days after last use by default). [^1][^9][^10] |
| Per-sandbox data | Usage per session after a clean stop: duration, activeCpuDurationMs, network bytes, sizeBytes for snapshots. No cost per sandbox; charges are per project per day. Not stated: delay or retention. [^8][^11][^12] |

## Not known yet

- Does Vercel bill provisioned memory from startedAt to stoppedAt, or from another moment?
  - To find out: Compare billed memory from the charges API with session duration, in a project running nothing else that day.
- Is a snapshot's sizeBytes the quantity billed as snapshot storage?
  - To find out: Compare the day's snapshot storage quantity with sizeBytes of the only snapshot in an idle project.
- Should a sandbox's cost include the snapshot kept after its last stop?
  - To find out: Measure its sizeBytes and the day's storage quantity before and after the stop, then decide if it belongs to the sandbox or the account.
- Where does a session end after a timeout, failure or direct delete?
  - To find out: Repeat the session-edge check with those stops and see if stoppedAt, duration and active CPU remain.
- Is Active CPU counted per vCPU or per sandbox, and is there a minimum?
  - To find out: Compare activeCpuDurationMs with billed Active CPU for 1 and 4 vCPU sandboxes running the same busy loop.
- Is GB in provisioned memory 1,000 or 1,024 MB?
  - To find out: Compare billed GB-hours for known memory and duration with 2 GB per vCPU as 2,000 and 2,048 MB.
- Is loading an uncached image billed?
  - To find out: Compare billed memory for a large image on first and second use over the same duration.
- Why was one data-transfer row charged $0.15 per GB while six others were $0?
  - To find out: Export the charges again with project tags kept to see whether the row belongs to another plan or project.

## Our measurements

- 2026-10-12: [Billing charges export against the price version's rates](evidence/2026-10-12-charges-rates-check.md). 25 of 26 daily charge rows equal quantity times the price version's rate; one small data-transfer row was charged $0.15 per GB, not $0. Checks rates and units only, not billing edges.
- 2026-10-11: [Session start and stop times against our call edges](evidence/2026-10-11-session-edges.md). In five sessions, startedAt fell inside the create call, stoppedAt preceded the destroy call, and duration equalled stoppedAt minus startedAt. No bill was compared, so the billed memory boundary is unsettled.

## Price versions

- [`vercel@2026-10-20`](../../src/sandbox_provider_pricing/providers/vercel/prices/2026-10-20.yaml): from 2026-10-18, read 2026-10-20, replaced by `vercel@2026-10-20-055630Z`.
- [`vercel@2026-10-20-055631Z`](../../src/sandbox_provider_pricing/providers/vercel/prices/2026-10-20-055631Z.yaml): from 2026-09-29, read 2026-10-20, in effect now.
- [`vercel@2026-10-20-055630Z`](../../src/sandbox_provider_pricing/providers/vercel/prices/2026-10-20-055630Z.yaml): from 2026-09-29, read 2026-10-20, replaced by `vercel@2026-10-20-055631Z`.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/vercel/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [vercel.com/docs/sandbox/pricing](https://vercel.com/docs/sandbox/pricing)
[^2]: [vercel.com/docs/rest-api/sandboxes/create-a-named-sandbox-1](https://vercel.com/docs/rest-api/sandboxes/create-a-named-sandbox-1)
[^3]: [2026-10-11-session-edges.md](evidence/2026-10-11-session-edges.md#verdict)
[^4]: [vercel.com/docs/sandbox/concepts/persistent-sandboxes](https://vercel.com/docs/sandbox/concepts/persistent-sandboxes)
[^5]: [vercel.com/docs/sandbox/concepts/snapshots](https://vercel.com/docs/sandbox/concepts/snapshots)
[^6]: [vercel.com/docs/sandbox/concepts/images](https://vercel.com/docs/sandbox/concepts/images)
[^7]: [2026-10-20-055630Z.yaml](../../src/sandbox_provider_pricing/providers/vercel/prices/2026-10-20-055630Z.yaml)
[^8]: [2026-10-12-charges-rates-check.md](evidence/2026-10-12-charges-rates-check.md)
[^9]: [vercel.com/docs/plans/pro-plan](https://vercel.com/docs/plans/pro-plan)
[^10]: [vercel.com/docs/container-registry/limits-and-pricing](https://vercel.com/docs/container-registry/limits-and-pricing)
[^11]: [vercel.com/docs/rest-api/sandboxes/get-a-session](https://vercel.com/docs/rest-api/sandboxes/get-a-session)
[^12]: [vercel.com/docs/rest-api/billing/list-focus-billing-charges](https://vercel.com/docs/rest-api/billing/list-focus-billing-charges)
