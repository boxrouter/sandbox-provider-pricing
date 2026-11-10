# E2B

E2B costs are `calculated`. The provider's own usage records priced at list rates.

E2B reports no cost. Each running period lasts from a created or resumed event to the next paused or killed event, and is priced at the list rates per second, with the size from the event's execution object when it has one. The events API keeps events for 7 days by default, so store them. The cost is calculated, not E2B's own figure.

## How the cost is worked out

For each running period, from a created or resumed event to the next paused or killed event: seconds × (vCPUs × CPU rate + GiB of memory × memory rate).

What holds it back: E2B reports no per-sandbox cost or billed usage, only lifecycle events, which are priced at list rates.

What would improve it: A per-sandbox cost or billed usage from E2B that matches the list-price calculation on measured sandboxes.

## Rates

From [`e2b@2026-10-31-015029Z`](../../src/sandbox_provider_pricing/providers/e2b/prices/2026-10-31-015029Z.yaml), in effect from 2026-10-11, default class `default`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| CPU | $0.000014 per vCPU-second | size requested | running |
| Memory | $0.0000045 per GiB-second | size requested | running |

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | vCPU-seconds and GiB-seconds of memory as allocated, while running. Disk is included in the plan (10 GiB Hobby, 20 GiB Pro), not a meter. Sandboxes are CPU-only. [^1][^2][^3][^4] |
| Billing starts | Not stated. The calculator uses E2B's created event, which fell inside the create call on five sandboxes. This does not show E2B bills from it. [^3][^5] |
| Billing ends | Billing stops immediately on pause, kill or timeout. The calculator uses the killed event, which fell inside the destroy call on five sandboxes. [^3][^5] |
| Rounding | Billed per second. No minimum duration or rounding increment is published. [^1][^2][^3] |
| Idle and paused | Only running time is billed. Paused sandboxes are kept with no time limit and are not billed. Whether pausing itself is billed has not been tested. [^3] |
| Image pull | Not stated. A cold large image's created event came 9.7 s after create was sent, inside the create call; we did not isolate an image-load charge. [^1][^3][^6] |
| Billed separately | None published: no creation fee, no paused-state or template storage charge. Network is not mentioned on the pricing or billing pages. [^1][^3] |
| Left out | Plan fees (Pro $150 per month, concurrency add-ons, Enterprise minimum), the one-time $100 Hobby credit and taxes. Plans cap vCPU and memory (8 each), and runtime (1 hour Hobby, 24 hours Pro). [^1][^3] |
| Per-sandbox data | No cost. Killed and paused events, from the events API or webhooks, carry the allocated vCPUs, memory and runtime. The console's usage tab shows totals only. The first killed event arrived within 15 s. Running time comes from event timestamps, not execution_time, which can under-report after a snapshot. [^2][^7][^8][^9] |

## Not known yet

- Are paused sandboxes free, and is the pause operation itself billed?
  - To find out: Pause one sandbox for a measured period and compare account usage before and after.
- Is loading a cold image billed?
  - To find out: Compare account usage for a cold large image against a cached one at known durations.
- Does E2B bill from its created and killed events, and does event execution time equal billed time?
  - To find out: Compare dashboard usage for a known set of sandboxes with event-derived running time.
- Do killed and paused events from the events API carry the execution fields? The docs example shows eventData null.
  - To find out: Read the events of a killed sandbox from the events API and check for the execution fields.
- How long are events kept? The events API page says 7 days; the webhooks example shows events_ttl_days 30.
  - To find out: Read events_ttl_days on webhook deliveries, then read a finished sandbox's events after 1, 7 and 30 days.
- Default memory? Pricing page marks 4 GiB default; billing page and price FAQ say 512 MiB.
  - To find out: Create a sandbox without a size and read its memory from inside it.
- What do the updated and snapshot events mean for billing? The calculator ignores them.
  - To find out: Update and snapshot one sandbox, read its events, and compare account usage with event-derived running time.
- Does the console usage tab show one project or the whole workspace? Is Pro disk above 20 GiB charged?
  - To find out: Run sandboxes in two projects and check the tab; check the Pro disk rate on the pricing and billing pages after a size above 20 GiB is requested.

## Our measurements

- 2026-10-11: [Billing boundary against E2B lifecycle events](evidence/2026-10-11-billing-boundary.md). On five sandboxes the created and killed events fell inside the matching create and destroy calls, including a cold large image; it did not compare against a billed figure or test pause.

## Price versions

- [`e2b@2026-10-31-015029Z`](../../src/sandbox_provider_pricing/providers/e2b/prices/2026-10-31-015029Z.yaml): from 2026-10-11, read 2026-10-31, in effect now.
- [`e2b@2026-10-31-015028Z`](../../src/sandbox_provider_pricing/providers/e2b/prices/2026-10-31-015028Z.yaml): from 2026-10-11, read 2026-10-31, replaced by `e2b@2026-10-31-015029Z`.
- [`e2b@2026-10-29-203000Z`](../../src/sandbox_provider_pricing/providers/e2b/prices/2026-10-29-203000Z.yaml): from 2026-10-11, read 2026-10-29, replaced by `e2b@2026-10-31-015028Z`.
- [`e2b@2026-10-20-061802Z`](../../src/sandbox_provider_pricing/providers/e2b/prices/2026-10-20-061802Z.yaml): from 2026-10-11, read 2026-10-20, replaced by `e2b@2026-10-29-203000Z`.
- [`e2b@2026-10-20`](../../src/sandbox_provider_pricing/providers/e2b/prices/2026-10-20.yaml): from 2026-10-11, read 2026-10-20, replaced by `e2b@2026-10-20-061802Z`.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/e2b/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [e2b.dev/pricing](https://e2b.dev/pricing)
[^2]: [docs.e2b.dev/faq/calculate-sandbox-price](https://docs.e2b.dev/faq/calculate-sandbox-price)
[^3]: [docs.e2b.dev/billing](https://docs.e2b.dev/billing)
[^4]: [docs.e2b.dev/faq/gpu-support](https://docs.e2b.dev/faq/gpu-support)
[^5]: [2026-10-11-billing-boundary.md](evidence/2026-10-11-billing-boundary.md#verdict)
[^6]: [2026-10-11-billing-boundary.md](evidence/2026-10-11-billing-boundary.md#results)
[^7]: [docs.e2b.dev/sandbox/lifecycle-events-api](https://docs.e2b.dev/sandbox/lifecycle-events-api)
[^8]: [docs.e2b.dev/sandbox/lifecycle-events-webhooks](https://docs.e2b.dev/sandbox/lifecycle-events-webhooks)
[^9]: [2026-10-11-billing-boundary.md](evidence/2026-10-11-billing-boundary.md#event-latency)
