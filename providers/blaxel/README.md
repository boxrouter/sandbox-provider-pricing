# Blaxel

Blaxel costs are `reported`. The provider's own cost for the sandbox, matching list price.

Blaxel's Billing Explorer metrics API reports each sandbox's cost, including standby snapshot storage. Those amounts matched list rates in our checks and are labelled reported. A missing or early record leaves the cost unknown until a later read.

## How the cost is worked out

Blaxel's own cost for the sandbox. Check: active seconds × GB of memory × memory rate (CPU is included), plus snapshot GB × seconds in standby × snapshot rate.

What holds it back: Nothing. In our checks Blaxel's per-sandbox cost matched list price, with compute in whole seconds and standby snapshot storage at its listed rate.

What would improve it: Nothing. Until Blaxel's metrics record arrives, the cost is unknown.

## Rates

From [`blaxel@2026-11-07-122300Z`](../../src/sandbox_provider_pricing/providers/blaxel/prices/2026-11-07-122300Z.yaml), in effect from 2026-10-18, default class `default`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| Memory | $0.0000115 per GB-second | only while in use | running |

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | Memory allocated at creation, per GB-second. CPU is not charged separately; it is allocated from the memory size. Our 4096 MiB sandbox was billed as 4 GB. [^1][^2][^3] |
| Billing starts | Measured at create returned. Create sent is not ruled out for creates of 0.2 to 0.4 s; the one 2.13 s create fitted create returned only. [^4] |
| Billing ends | Measured at destroy returned. Destroy sent is ruled out, as it would make the batch 1.8% shorter than billed. [^4] |
| Rounding | Compute in whole seconds, truncated; every compute cost was a whole number of seconds at the list rate. Standby snapshot storage is added per second, so a total is not always whole seconds. No minimum or increment is stated on the pricing page. [^1][^4][^5] |
| Idle and paused | Active is billed. Without an active connection a sandbox enters standby, where memory is not billed but snapshot storage is. Blaxel's pages say about 5 s or 15 s to standby, and we measured 22.7 to 34.8 s. Archived is "you stop paying for it". Paused and stopped are not stated. [^1][^2][^5][^6][^7] |
| Image pull | Unknown for a cold, large custom image; not stated. Our check used a cached standard image and Blaxel's base image (creates took 0.2 to 0.4 s, one 2.13 s). A brought image must be built in the workspace. To find out: Build a large custom image in the workspace, create sandboxes from it and compare billed seconds with create sent and create returned. |
| Billed separately | Snapshots $0.20, deployment images $0.045 and volumes $0.12, each per GiB-month. The sandbox's own disk has no separate charge, because its writable layer lives in the allocated memory that is billed. No creation fee or GPU price is stated. Egress is listed as included. [^1][^8][^9] |
| Left out | Up to $200 free credits, tier top-ups (prepaid usage), support add-ons, custom domains, image and volume storage, and taxes. Standby snapshot storage is included in the reported cost. Whether free credit is drawn at list rates is not stated. [^1][^10] |
| Per-sandbox data | Yes. The metrics API gives each sandbox's cost by billing dimension, in hourly buckets at finest. Blaxel says figures take "a few minutes, sometimes longer". Ours appeared about 50 s after create and were final 45 to 113 s after destroy, then unchanged for over 30 minutes. Read every page of the response. [^3][^5][^9][^11] |

## Not known yet

- Is loading a cold, large custom image billed as sandbox time?
  - To find out: Build a large image into the workspace, create sandboxes from it and compare billed seconds with create sent and create returned.
- Does billing start at create sent or create returned?
  - To find out: Repeat with creates of several seconds so the two edges differ by more than whole-second truncation.
- Which instants count as active for the standby discount?
  - To find out: Hold sandboxes with timed connections and idle gaps, then compare billed seconds with connected time.
- How long does the metrics API keep a sandbox's figure, and does it settle later under load?
  - To find out: Read figures for sandboxes of several ages up to the API's 7-day window, and repeat the lag timing on a busy hour.
- Does a sandbox's reported cost include image storage? Standby snapshot storage was included; no image storage row appeared.
  - To find out: Read metrics with groupBy=resource_uuid,billing_dimension for a sandbox made from a custom image.
- How many CPU cores does a 16 GB sandbox get? The overview says 6; the API reference formula gives 8.
  - To find out: Create a 16 GB sandbox and count its cores.
- Is the stored filesystem of an archived sandbox billed?
  - To find out: Archive a sandbox and read its billing dimensions over the following days.

## Our measurements

- 2026-10-11: [Billing boundary and standby against per-sandbox metrics](evidence/2026-10-11-billing-boundary.md). 25 sandboxes fit create returned to destroy returned, whole seconds truncated, at list rate. 21 rows fit one by one and 4 differed by under 0.7 s. Standby time was billed for less than the sandbox's life. No cold large image was tested, and create sent is not ruled out.
- 2026-10-20: [Time to standby and metrics lag against per-sandbox metrics](evidence/2026-10-20-standby-and-metrics-lag.md). 8 idle sandboxes were billed compute for 22.7 to 34.8 s after their last command, then standby; standby billed snapshot storage at the listed rate. Each cost was final 45 to 113 s after destroy and then unchanged.

## Price versions

- [`blaxel@2026-11-07-122300Z`](../../src/sandbox_provider_pricing/providers/blaxel/prices/2026-11-07-122300Z.yaml): from 2026-10-18, read 2026-11-07, in effect now.
- [`blaxel@2026-10-29-023001Z`](../../src/sandbox_provider_pricing/providers/blaxel/prices/2026-10-29-023001Z.yaml): from 2026-10-18, read 2026-10-29, replaced by `blaxel@2026-11-07-122300Z`.
- [`blaxel@2026-10-29-023000Z`](../../src/sandbox_provider_pricing/providers/blaxel/prices/2026-10-29-023000Z.yaml): from 2026-10-18, read 2026-10-29, replaced by `blaxel@2026-10-29-023001Z`.
- [`blaxel@2026-10-23-032207Z`](../../src/sandbox_provider_pricing/providers/blaxel/prices/2026-10-23-032207Z.yaml): from 2026-10-18, read 2026-10-23, replaced by `blaxel@2026-10-29-023000Z`.
- [`blaxel@2026-10-20-061947Z`](../../src/sandbox_provider_pricing/providers/blaxel/prices/2026-10-20-061947Z.yaml): from 2026-10-18, read 2026-10-20, replaced by `blaxel@2026-10-23-032207Z`.
- [`blaxel@2026-10-20`](../../src/sandbox_provider_pricing/providers/blaxel/prices/2026-10-20.yaml): from 2026-10-18, read 2026-10-20, replaced by `blaxel@2026-10-20-061947Z`.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/blaxel/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [blaxel.ai/pricing](https://blaxel.ai/pricing)
[^2]: [docs.blaxel.ai/Sandboxes/Overview](https://docs.blaxel.ai/Sandboxes/Overview)
[^3]: [2026-10-11-billing-boundary.md](evidence/2026-10-11-billing-boundary.md#method)
[^4]: [2026-10-11-billing-boundary.md](evidence/2026-10-11-billing-boundary.md#verdict)
[^5]: [2026-10-20-standby-and-metrics-lag.md](evidence/2026-10-20-standby-and-metrics-lag.md#verdict)
[^6]: [docs.blaxel.ai/Sandboxes/Archive](https://docs.blaxel.ai/Sandboxes/Archive)
[^7]: [2026-10-11-billing-boundary.md](evidence/2026-10-11-billing-boundary.md#standby-earlier-batch-same-day)
[^8]: [blaxel.ai/platform/storage](https://blaxel.ai/platform/storage)
[^9]: [docs.blaxel.ai/api-reference/billing](https://docs.blaxel.ai/api-reference/billing)
[^10]: [docs.blaxel.ai/Security/Quotas](https://docs.blaxel.ai/Security/Quotas)
[^11]: [docs.blaxel.ai/Security/Billing-Explorer-API](https://docs.blaxel.ai/Security/Billing-Explorer-API)
