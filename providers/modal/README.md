# Modal

Modal costs are `reported`. The provider's own cost for the sandbox, matching list price.

Modal bills per App and hour, not per sandbox. When the caller proves an App held only the target sandbox, the sandbox's cost is the sum of its hourly USD rows; a missing row is zero only when the recorded request window covers that hour. The report is read at least 600 seconds after Modal's finished_at. In 325 one-sandbox Apps the rows stayed readable after the App stopped, and their totals were a little below the list price of created_at to finished_at. How long rows are kept is not verified.

## How the cost is worked out

Modal's own bill for the App, when it held only this sandbox: the sum of hourly USD rows and covered empty hours, read at least 600 seconds after finished_at. An image preparation is priced the same way from its own stopped App. Otherwise unknown.

What holds it back: Nothing. The figure counts only for an App proven to hold this one sandbox, with its report read at least 600 seconds after Modal's finished_at and its request window covering every billed hour.

What would improve it: Nothing. A shared App, an uncovered missing hour, another workspace or environment, or a read too early leaves the cost unknown.

## Rates

From [`modal@2026-11-05-065701Z`](../../src/sandbox_provider_pricing/providers/modal/prices/2026-11-05-065701Z.yaml), in effect from 2026-10-11, default class `default`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| CPU | $0.00003942 per core-second | larger of requested and used | running |
| Memory | $0.00000667 per GiB-second | larger of requested and used | running |
| Network egress | $0.04 per GiB |  |  |
| GPU | per GPU model (11 models in the price version) | size requested | running |

Region multipliers when a region is chosen: us x1.15, us-west x1.75.

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | CPU (physical cores, 1 core = 2 vCPUs) and memory (GiB), each on the larger of requested and actual use. No sandbox cost is calculated from the request. Minimum request 0.125 cores and 128 MiB. [^1][^2][^3] |
| Billing starts | Measured on 2026-10-11, not complete. Billing starts at about when Modal sets the sandbox's creation time, 20 to 70 ms before the create call returns. It does not start when the call is sent. [^4] |
| Billing ends | At Modal's finished_at, measured on 325 one-sandbox Apps; each App's bill stopped growing then, and its final rows appeared within 315 seconds. The exact edge and rounding are unsettled, as the median bill was 2.22 seconds below created_at to finished_at at list rates. [^5] |
| Rounding | Billed per second, and Modal's billing page lists no minimum time increment. How a partial second is rounded is not stated. [^1][^6] |
| Idle and paused | Not stated for sandboxes. The pricing page bills a 60-second default keep-alive for applications that take inputs, but does not say whether it applies to sandboxes. Sandboxes have a timeout (5 minutes by default, up to 24 hours) and an optional idle timeout, neither tied to billing. We have not measured this. [^1][^2][^7] |
| Image pull | Modal's pages do not say. In our check, five cold images with pulls of 20 to 133 s were not billed (620 s billed against 611 s from create returned and 1,016 s from create sent). [^1][^8] |
| Billed separately | Region multiplier on CPU, memory and GPU of 1.15 (broad region) or 1.75 (narrow region). Egress $0.04 per GiB above a workspace allowance, billed from 2026-10-01. Volumes $0.09 per GiB-month. GPUs per second by model. No snapshot or image storage price is stated. [^1][^9][^10][^11] |
| Left out | Plan fees (Starter $0, Team $250 per month), monthly free credits, credit programs, discounts, taxes, and the egress allowance. The list-price figure also leaves out volumes, snapshot retention and egress. [^1][^12] |
| Per-sandbox data | Workspace.billing.report gives each App's hourly USD total and its cost per resource, with no sandbox ID. The recorded request window lets us identify covered hours with no returned row. Rows stayed readable after the App stopped, so stop each App to stay within the 200 deployed Apps a workspace allows. Retention past 2 h 5 min is untested. [^5][^6][^13] |

## Not known yet

- Are a stopped image-preparation App's lifecycle, layout and sandbox list populated and stable, so its rows can be priced?
  - To find out: Build an image in its own App, stop it, then read AppGetLifecycle, AppGetLayout and the finished sandbox list; until then preparations stay unknown.
- Does actual CPU or memory use above its request add to a sandbox's bill?
  - To find out: Run workloads that exceed their requests, each in its own App, and compare billed rows with the requested-size rate.
- Why is the reported amount below the created_at-to-finished_at list-rate price by 2.22 seconds at the median?
  - To find out: Repeat isolated CPU-only and memory-heavy cases in a region without a multiplier and compare provider times with the hourly bill.
- How long are App billing rows retained, and can Modal revise them after the observed window?
  - To find out: Re-read stopped-App rows beyond 2 hours 5 minutes after hour close and record any later changes or disappearance.
- Does the 60-second keep-alive described for applications apply to sandboxes?
  - To find out: Compare a sandbox's hourly App rows with its provider lifecycle span after it has been idle for over 60 seconds.
- Do a GPU sandbox's CPU and memory bill at the Sandbox rate or the standard rate?
  - To find out: Compare the hourly bill of a per-App GPU sandbox with its CPU and memory priced at each rate.

## Our measurements

- 2026-10-24: [Per-sandbox cost through one Modal App per sandbox](evidence/2026-10-23-per-app-bill.md). Each of 325 Apps held one sandbox, and the rows of the six sandboxes that crossed an hour summed correctly. Final values appeared within 315 seconds of the sandbox's end and did not change before the last read. Longer retention was not tested.
- 2026-10-11: [Billing boundary against the hourly per-App bill](evidence/2026-10-11-hourly-bill-batch.md). 20 cached and 5 cold sandboxes. Image pulls were not billed and billing starts at about create returned. The end edge is unresolved, and the bill is 1.3% below (cached) and 1.5% above (cold) the shortest edge-based total.

## Price versions

- [`modal@2026-11-05-065701Z`](../../src/sandbox_provider_pricing/providers/modal/prices/2026-11-05-065701Z.yaml): from 2026-10-11, read 2026-11-05, in effect now.
- [`modal@2026-11-05-065700Z`](../../src/sandbox_provider_pricing/providers/modal/prices/2026-11-05-065700Z.yaml): from 2026-10-11, read 2026-11-05, replaced by `modal@2026-11-05-065701Z`.
- [`modal@2026-11-05-055300Z`](../../src/sandbox_provider_pricing/providers/modal/prices/2026-11-05-055300Z.yaml): from 2026-10-11, read 2026-11-05, replaced by `modal@2026-11-05-065700Z`.
- [`modal@2026-10-30-103442Z`](../../src/sandbox_provider_pricing/providers/modal/prices/2026-10-30-103442Z.yaml): from 2026-10-11, read 2026-10-30, replaced by `modal@2026-11-05-055300Z`.
- [`modal@2026-10-29-163500Z`](../../src/sandbox_provider_pricing/providers/modal/prices/2026-10-29-163500Z.yaml): from 2026-10-11, read 2026-10-29, replaced by `modal@2026-10-30-103442Z`.
- [`modal@2026-10-24-065000Z`](../../src/sandbox_provider_pricing/providers/modal/prices/2026-10-24-065000Z.yaml): from 2026-10-11, read 2026-10-24, replaced by `modal@2026-10-29-163500Z`.
- [`modal@2026-10-20-061900Z`](../../src/sandbox_provider_pricing/providers/modal/prices/2026-10-20-061900Z.yaml): from 2026-10-11, read 2026-10-20, replaced by `modal@2026-10-24-065000Z`.
- [`modal@2026-10-20`](../../src/sandbox_provider_pricing/providers/modal/prices/2026-10-20.yaml): from 2026-10-11, read 2026-10-20, replaced by `modal@2026-10-20-061900Z`.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/modal/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [modal.com/pricing](https://modal.com/pricing)
[^2]: [modal.com/docs/guide/sandbox-resources](https://modal.com/docs/guide/sandbox-resources)
[^3]: [modal.com/docs/guide/resources](https://modal.com/docs/guide/resources)
[^4]: [2026-10-11-hourly-bill-batch.md](evidence/2026-10-11-hourly-bill-batch.md#verdict)
[^5]: [2026-10-23-per-app-bill.md](evidence/2026-10-23-per-app-bill.md#verdict)
[^6]: [modal.com/docs/guide/billing](https://modal.com/docs/guide/billing)
[^7]: [modal.com/docs/guide/sandboxes](https://modal.com/docs/guide/sandboxes)
[^8]: [2026-10-11-hourly-bill-batch.md](evidence/2026-10-11-hourly-bill-batch.md#results)
[^9]: [modal.com/docs/guide/region-selection](https://modal.com/docs/guide/region-selection)
[^10]: [modal.com/docs/guide/network-egress-billing](https://modal.com/docs/guide/network-egress-billing)
[^11]: [modal.com/docs/guide/sandbox-snapshots](https://modal.com/docs/guide/sandbox-snapshots)
[^12]: [2026-10-20-061900Z.yaml](../../src/sandbox_provider_pricing/providers/modal/prices/2026-10-20-061900Z.yaml)
[^13]: [2026-10-23-per-app-bill.md](evidence/2026-10-23-per-app-bill.md#limits)
