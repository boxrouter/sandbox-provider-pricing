# Daytona

Daytona costs are `reported`. The provider's own cost for the sandbox, matching list price.

Daytona's analytics API returns a price and billed periods for each sandbox. Those prices matched list rates in our checks and are labelled reported; without a record the cost is unknown. Early reads ran low, so re-read until 72 hours after the sandbox ends.

## How the cost is worked out

Daytona's own price for the sandbox. Check: billed seconds × (vCPUs × CPU rate + GiB of memory × memory rate + GiB of disk × disk rate).

What holds it back: Nothing. In three samples the first read of a price was 2.73% to 4.25% below a later read, so the price is read again until 72 hours after the sandbox ends.

What would improve it: Nothing. Without Daytona's per-sandbox analytics record the cost is unknown.

## Rates

From [`daytona@2026-10-24-065001Z`](../../src/sandbox_provider_pricing/providers/daytona/prices/2026-10-24-065001Z.yaml), in effect from 2026-10-18, default class `on-demand`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| CPU | $0.0504 per vCPU-hour | size requested | running |
| Memory | $0.0162 per GiB-hour | size requested | running |
| Disk | $0.000108 per GiB-hour | size requested | running, paused, stopped |
| GPU | per GPU model (8 models in the price version) | size requested | running |

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | CPU, memory and disk as reserved, not as used. Disk is charged in full; the pricing page says "after first 5 free", but the reported prices we measured deducted none. [^1][^2][^3] |
| Billing starts | At create returned, measured on seven sandboxes. Daytona's first period began 14 to 86 ms earlier, within network and clock error. [^4] |
| Billing ends | At destroy sent, measured on seven sandboxes. Daytona's last period ended 28 to 68 ms later. [^4] |
| Rounding | Not stated beyond "calculated per second". Billed periods have millisecond edges, and a 247 ms period was priced at its exact length. [^1][^2][^5] |
| Idle and paused | Stopped and paused (VM only) are billed for disk only. Archived (container only) and deleted are not billed. Creating, starting, stopping and pausing bill like started. Paused and archived were not measured. [^2][^5] |
| Image pull | Not stated. One 27.9 s create that built or pulled an image was not billed; only one long create was measured. [^2][^5] |
| Billed separately | Not stated for network or creation. GPU is priced per GPU-hour (for example H100 $3.95 on-demand) and Windows at $0.0858 per vCPU-hour. Snapshots made from a sandbox stay billed after deletion, with no published rate. [^1][^2][^6] |
| Left out | Free credit, plan or tier fees, taxes, discounts, GPU and Windows sandboxes, snapshot and image storage, and any network charge. Volumes are included at no extra cost. [^1][^2][^7] |
| Per-sandbox data | Yes. The analytics API gives each sandbox's price and billed periods. The billing page says charges can take up to 48 hours to appear; whether this applies to the API is not stated. [^2][^8][^9] |

## Not known yet

- Is the "first 5 GiB free" disk allowance per sandbox, per organization or only on the invoice? Measured prices charged all disk.
  - To find out: Compare a sandbox's reported price with the organization's invoice for a period with several sandboxes.
- Why were first reads of the per-sandbox price 2.73% to 4.25% lower than later reads?
  - To find out: Read the per-sandbox endpoint repeatedly after a sandbox ends until the price stops changing.
- Is a larger cold image build or pull also unbilled, in other sizes and regions?
  - To find out: Repeat the boundary check with fresh images of several sizes and compare the first billed period with create returned.
- How are paused VM and archived container sandboxes billed in practice?
  - To find out: Pause a VM sandbox and archive a container sandbox, then compare their billed periods with the billing page.
- At what rate are snapshots made from a sandbox billed?
  - To find out: Compare an invoice before and after creating a snapshot.
- Do per-sandbox figures change after the first 20 minutes, and how long are they kept?
  - To find out: Read a finished sandbox at set intervals up to 72 hours, then after 30 and 90 days. Arrival was measured on 2026-10-24 (at most 68.2 s after destroy returned).

## Our measurements

- 2026-10-24: [How soon a finished sandbox's analytics row arrives](evidence/2026-10-24-analytics-row-latency.md). On 10 sandboxes that ran 5 to 300 s, each row was readable at most 9.4 to 68.2 s after destroy returned, already final for the next 20 minutes, and priced at list rates. One organization, one size.
- 2026-10-11: [Billing boundary against Daytona's billed periods](evidence/2026-10-11-billing-boundary.md). On seven sandboxes Daytona's billed periods began just before create returned and ended just after destroy was sent, and every price matched list rates. One organization, container sandboxes only.
- 2026-10-05: [Reported price against the list-price calculation](evidence/2026-10-05-reported-vs-list-price.md). On three 5-second sandboxes our list-price calculation was 1.06% to 1.80% below Daytona's price. The first read of each price was 2.73% to 4.25% lower than a later one; the cause is unknown.

## Price versions

- [`daytona@2026-10-24-065001Z`](../../src/sandbox_provider_pricing/providers/daytona/prices/2026-10-24-065001Z.yaml): from 2026-10-18, read 2026-10-24, in effect now.
- [`daytona@2026-10-24-065000Z`](../../src/sandbox_provider_pricing/providers/daytona/prices/2026-10-24-065000Z.yaml): from 2026-10-18, read 2026-10-24, replaced by `daytona@2026-10-24-065001Z`.
- [`daytona@2026-10-20-061942Z`](../../src/sandbox_provider_pricing/providers/daytona/prices/2026-10-20-061942Z.yaml): from 2026-10-18, read 2026-10-20, replaced by `daytona@2026-10-24-065000Z`.
- [`daytona@2026-10-20`](../../src/sandbox_provider_pricing/providers/daytona/prices/2026-10-20.yaml): from 2026-10-18, read 2026-10-20, replaced by `daytona@2026-10-20-061942Z`.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/daytona/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [daytona.io/pricing](https://www.daytona.io/pricing)
[^2]: [daytona.io/docs/en/billing](https://www.daytona.io/docs/en/billing/)
[^3]: [2026-10-11-billing-boundary.md](evidence/2026-10-11-billing-boundary.md#price-against-list-rates)
[^4]: [2026-10-11-billing-boundary.md](evidence/2026-10-11-billing-boundary.md#verdict)
[^5]: [2026-10-11-billing-boundary.md](evidence/2026-10-11-billing-boundary.md#results)
[^6]: [daytona.io/docs/en/sandboxes](https://www.daytona.io/docs/en/sandboxes/)
[^7]: [daytona.io/docs/en/volumes](https://www.daytona.io/docs/en/volumes/)
[^8]: [analytics.app.daytona.io/swagger/index.html](https://analytics.app.daytona.io/swagger/index.html)
[^9]: [2026-10-05-reported-vs-list-price.md](evidence/2026-10-05-reported-vs-list-price.md#verdict)
