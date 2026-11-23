# Beam

Beam costs are `unknown`. No provider evidence gives a figure, so there is no cost. The total is `null`.

Billing rules have not been verified. Unknown facts remain unpriced.

## How the cost is worked out

Unknown until the provider's meters and billing boundaries are verified.

What holds it back: Beam documents no per-sandbox usage or cost record (SDK, gateway REST and platform API read 2026-11-23), so there is nothing to compare a sandbox's cost against.

What would improve it: A per-sandbox usage or cost record from Beam, compared with the published list rates in a recorded run.

## Rates

From [`beam@2026-11-23`](../../src/sandbox_provider_pricing/providers/beam/prices/2026-11-23.yaml), in effect from 2026-11-23, default class `default`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| CPU | $0.05 per vCPU-hour | size requested | running |
| Memory | $0.01 per GiB-hour | size requested | running |

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | $0.05 per vCPU-hour and $0.01 per GiB-hour of the size the sandbox is allocated, while it is running, on the Performance tier (the default for new accounts). Shared and Spot tiers have lower rates and are not priced here. [^1][^2] |
| Billing starts | Unknown; not yet verified. To find out: Read the provider's billing documentation and verify its records. |
| Billing ends | Unknown; not yet verified. To find out: Read the provider's billing documentation and verify its records. |
| Rounding | Billed by the millisecond; no minimum or rounding increment is stated. [^1] |
| Idle and paused | Unknown; not yet verified. To find out: Read the provider's billing documentation and verify its records. |
| Image pull | Waiting for a machine to start and pulling the container image are not charged. The billing page states this under serverless compute; it does not repeat it for sandboxes. [^2] |
| Billed separately | Unknown; not yet verified. To find out: Read the provider's billing documentation and verify its records. |
| Left out | Unknown; not yet verified. To find out: Read the provider's billing documentation and verify its records. |
| Per-sandbox data | Unknown; not yet verified. To find out: Read the provider's billing documentation and verify its records. |

## Not known yet

Nothing open.

## Our measurements

None yet.

## Price versions

- [`beam@2026-11-23`](../../src/sandbox_provider_pricing/providers/beam/prices/2026-11-23.yaml): from 2026-11-23, read 2026-11-23, in effect now.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/beam/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [beam.cloud/pricing](https://www.beam.cloud/pricing)
[^2]: [docs.beam.cloud/v2/resources/pricing-and-billing](https://docs.beam.cloud/v2/resources/pricing-and-billing)
