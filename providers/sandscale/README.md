# Sandscale

Sandscale costs are `unknown`. No provider evidence gives a figure, so there is no cost. The total is `null`.

Plans include monthly awake vCPU-hours; on Pro and Team, use beyond them can be billed per awake vCPU-hour. Memory up to 4 GiB per vCPU is included.

## How the cost is worked out

vCPUs of the box times its awake hours, at the cpu rate, once a paid plan's included hours are used and usage beyond them is on.

What holds it back: Only the pricing page has been read (2026-11-27); no per-sandbox usage or cost record from Sandscale has been compared with the list rate.

What would improve it: A recorded run whose per-sandbox awake time or charge from Sandscale is compared with the published rate.

## Rates

From [`sandscale@2026-11-27`](../../src/sandbox_provider_pricing/providers/sandscale/prices/2026-11-27.yaml), in effect from 2026-11-27, default class `default`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| CPU | $0.05 per vCPU-hour | only while in use | running |
| Memory | $0 per GiB-hour | size requested | running |

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | $0.05 per vCPU-hour for each vCPU of the box while it is awake, on Pro and Team once the included hours are used and usage beyond them is turned on. Memory up to 4 GiB per vCPU is included. [^1] |
| Billing starts | Not stated on the pricing page. [^1] |
| Billing ends | Not stated on the pricing page. [^1] |
| Rounding | Not stated on the pricing page; no increment or minimum is given for awake time. [^1] |
| Idle and paused | A box that is paused, or idle between tool calls, does not count toward awake vCPU-hours. [^1] |
| Image pull | Not stated on the pricing page. [^1] |
| Billed separately | Memory above 4 GiB per vCPU counts as extra vCPU-hours (4 GiB-hours of extra memory is 1 vCPU-hour). Storage above the plan allowance is billed to the account. [^1] |
| Left out | Plan fees, included hours, hour packs, account storage and optional add-ons are outside a sandbox's own cost. [^1] |
| Per-sandbox data | Unknown; the pricing page does not say whether a per-sandbox usage or cost record is available. To find out: Read a sandbox's usage through the Sandscale API after a recorded run and compare it with the awake time. |

## Not known yet

- What does a sandbox with more than 4 GiB of memory per vCPU cost?
  - To find out: The pricing page counts 4 GiB-hours of extra memory as 1 vCPU-hour; a memory rate, or a recorded run with extra memory, would price it.
- What does burst above a box's base size cost per sandbox?
  - To find out: Burst counts only the CPU used above the base; a usage record with burst CPU would be needed to price it.

## Our measurements

None yet.

## Price versions

- [`sandscale@2026-11-27`](../../src/sandbox_provider_pricing/providers/sandscale/prices/2026-11-27.yaml): from 2026-11-27, read 2026-11-27, in effect now.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/sandscale/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [sandscale.dev/pricing](https://sandscale.dev/pricing)
