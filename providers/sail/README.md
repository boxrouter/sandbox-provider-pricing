# Sail

Sail costs are `reported`. The provider's own cost for the sandbox, matching list price.

Sail's spend API reports each Sailbox's used vCPU seconds, memory GiB seconds and disk GiB seconds and the cost it works out from them at its published rates, as a per-Sailbox record and an account total. The figure is reported in batches of about a minute and settled 31.7 to 180.3 s after the end in measured sandboxes. Without a record the cost is unknown.

## How the cost is worked out

Sail's own cost_usd_nanos for the Sailbox, from GET /sailboxes/spend, read after it is final. Check: used vCPU seconds × CPU rate + used memory GiB seconds × memory rate + used disk GiB seconds × disk rate.

What holds it back: Nothing above the provider's own figure exists. A Sailbox's spend record settled within 180.3 s of its end in 16 measured sandboxes and equalled its own usage seconds times its published rates to rounding.

What would improve it: Nothing. A Sailbox with no spend record is read again until the record is final, then left unknown; list prices are never used to make one.

## Rates

From [`sail@2026-11-23`](../../src/sandbox_provider_pricing/providers/sail/prices/2026-11-23.yaml), in effect from 2026-11-23, default class `default`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| CPU | $0.015 per vCPU-hour | only while in use | running |
| Memory | $0.008 per GiB-hour | only while in use | running |
| Disk | $0.0007 per GiB-hour | only while in use | running |
| Creation | $0.01 per creation |  |  |

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | $0.015 per vCPU-hour of CPU time the Sailbox's virtual CPUs use, $0.008 per GiB-hour of physical RAM it holds (including its Linux filesystem cache, capped at its memory limit) and $0.0007 per GiB-hour of NVMe disk it uses, while it runs. A size is a ceiling, not a charge: used CPU, memory and disk are billed, not what is allocated. [^1][^2] |
| Billing starts | Cold-starting time is not billed. Billed running seconds were within 1 s of the time between the create returning and the destroy, except for a first partial batch. [^1][^3] |
| Billing ends | Billing stops when the Sailbox stops running. Sleeping, paused and checkpointing time is not billed. A terminate ends it at once. [^1] |
| Rounding | Usage is sampled every second and not rounded up to whole minutes; the spend API reports usage seconds with nine decimals and costs in whole billionths of a dollar. [^1][^4] |
| Idle and paused | An idle running Sailbox bills the CPU, memory and disk it uses. Sleeping and paused Sailboxes are not billed. [^1] |
| Image pull | Not stated; the pricing page says cold-starting time is not billed and does not break out image load time. To find out: Compare billed running seconds for a Sailbox from a cold image with one from a cached image at known durations. |
| Billed separately | Creation costs $0.01 per creation per new Sailbox on the Free plan and is waived on Pro and Enterprise. Volume storage costs $0.000411 per GiB-hour for each hour a volume exists. No egress charge is published. [^1] |
| Left out | Volume storage (BoxRouter creates no volume), plan fees and credits, and taxes. [^1] |
| Per-sandbox data | GET /sailboxes/spend with a sailbox_id returns the Sailbox's cost, running, vCPU, memory and disk seconds and creation count in its own units; terminated Sailboxes keep a record. The reads share one rate limit with Sail's other fleet reads and answer 429 with Retry-After when it is exceeded. [^1][^3] |

## Not known yet

- Is the creation charge part of cost_usd_nanos on an organization that pays it? The measured organization has creation fees waived and every record showed creation_count 0.
  - To find out: On an organization that does not waive creation fees, create one Sailbox and compare its cost_usd_nanos with usage times the rates plus the $0.01 creation charge.
- Can a Sailbox's spend record change after it is final?
  - To find out: Re-read measured Sailboxes' spend records daily for a week and compare the figures.
- Is image load or restore time billed?
  - To find out: Compare billed running seconds for a Sailbox from a cold image with one from a cached image at known durations.
- Is the account total in the spend API exactly the sum of the per-Sailbox figures?
  - To find out: Read the account total over a window and the sum of the per-Sailbox breakdown of the same window after both are settled.

## Our measurements

- 2026-11-23: [Settle lag of the per-Sailbox spend record](evidence/2026-11-23-settle-lag.md). 16 Sailboxes of 3 to 150 s lifetimes each had a spend record that stopped moving 31.7 to 180.3 s after the destroy returned. One organization, one region, the base image, 1 vCPU.
- 2026-11-23: [Cost against the spend API and usage times rates](evidence/2026-11-23-cost-vs-spend.md). One 60 s Sailbox with a known workload read through the adapter ended with a cost equal to the spend API total and to its usage times the published rates to rounding. One organization, one Sailbox.

## Price versions

- [`sail@2026-11-23`](../../src/sandbox_provider_pricing/providers/sail/prices/2026-11-23.yaml): from 2026-11-23, read 2026-11-23, in effect now.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/sail/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [docs.sailresearch.com/sailboxes-pricing.md](https://docs.sailresearch.com/sailboxes-pricing.md)
[^2]: [2026-11-23-cost-vs-spend.md](evidence/2026-11-23-cost-vs-spend.md#verdict)
[^3]: [2026-11-23-settle-lag.md](evidence/2026-11-23-settle-lag.md#results)
[^4]: [2026-11-23-cost-vs-spend.md](evidence/2026-11-23-cost-vs-spend.md#results)
