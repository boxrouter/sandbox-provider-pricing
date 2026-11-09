# Billing boundary against Modal's hourly per-App bill

**Date:** 2026-10-11. **Provider:** Modal. **Result:** Billing excludes the image pull and starts at about the moment Modal's own `created_at` is set, which is also about when the create call returns; the end edge could not be told apart between destroy sent and destroy returned, and the bill sits 1.3% below (cached) and 1.5% above (cold) the shortest edge-based total for a reason this check could not explain.

## Question

When does Modal start and stop billing a sandbox relative to our create and destroy calls, and is the time spent pulling an image billed? Modal's documentation says sandboxes are billed per second on the larger of requested and actual use, but does not say whether scheduling, image pull or termination is billed. Modal reports no per-sandbox cost, so the check compares the sum over a batch of sandboxes with the hourly per-App bill.

## Method

- **Sandboxes:** 25 in total, each with 2 physical cores (`cpu=(2,2)`, a request and a limit of 2), 4096 MiB memory, region `us`, runtime `gvisor`.
  - **Cached case (rows 1 to 20):** 20 sandboxes in one private App, all created within one UTC hour (12:00). Image: Modal's default image (`provider_default`), already used by this workspace.
  - **Cold case (rows 21 to 25):** 5 sandboxes, each in its own private App, all within the 13:00 UTC hour. Each used a different public image never pulled by this workspace before: tensorflow 2.16.1, pytorch 2.3.1 cuda, jupyter datascience-notebook, anaconda3, and nvidia/cuda 12.4.1 devel. Modal pulls the image inside the create call.
- **What we did:** each sandbox was created, held for 120 s, then destroyed (`terminate(wait=True)`), through BoxRouter's adapter for Modal on Modal SDK 1.6.0. A private App per case (per image in the cold case) keeps the hour's bill separate from other work.
- **Our times:** for every call, the moment it was sent and the moment it returned, from our own clock.
- **The provider's figures:**
  - `created_at` (called `createdAt` in the table) and `finished_at` (`finishedAt`) from Modal's sandbox list call with finished sandboxes included, read after each sandbox ended. These are times Modal returned; they are not our clock. No start, ready or enqueue time came back (see "Limits").
  - The bill: `modal.billing.workspace_billing_report`, hourly, per App, read after the hour ended. Billed seconds are the bill divided by $0.00012135 per second, which is 1.15 x (2 x $0.00003942 + 4 x $0.00000667): the `us` region multiplier of 1.15 applied to both CPU and memory, with memory at 4 GiB. Modal's [region-selection page](https://modal.com/docs/guide/region-selection) applies the multiplier to CPU, memory and GPU together in its worked example.
- Times in milliseconds unless stated. Offsets are Modal's figure minus our edge; negative means Modal's figure came first.

## Results

| # | Case | create call (ms) | `createdAt` − create sent (ms) | `createdAt` − create returned (ms) | `finishedAt` − destroy sent (ms) | `finishedAt` − destroy returned (ms) | create returned → destroy sent (s) | create sent → destroy returned (s) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Cached (provider_default) | 191 | 141 | -50 | 273 | -19 | 122.208 | 122.691 |
| 2 | Cached (provider_default) | 188 | 139 | -49 | 276 | -19 | 121.809 | 122.292 |
| 3 | Cached (provider_default) | 176 | 137 | -40 | 169 | -15 | 121.386 | 121.746 |
| 4 | Cached (provider_default) | 165 | 132 | -33 | 138 | -16 | 122.805 | 123.124 |
| 5 | Cached (provider_default) | 171 | 130 | -41 | 141 | -15 | 121.597 | 121.924 |
| 6 | Cached (provider_default) | 170 | 130 | -40 | 166 | -19 | 121.578 | 121.933 |
| 7 | Cached (provider_default) | 163 | 130 | -33 | 205 | -15 | 121.683 | 122.066 |
| 8 | Cached (provider_default) | 180 | 132 | -48 | 299 | -18 | 121.779 | 122.276 |
| 9 | Cached (provider_default) | 169 | 128 | -40 | 140 | -13 | 121.597 | 121.919 |
| 10 | Cached (provider_default) | 159 | 127 | -32 | 181 | -14 | 120.932 | 121.287 |
| 11 | Cached (provider_default) | 176 | 127 | -49 | 125 | -14 | 121.385 | 121.701 |
| 12 | Cached (provider_default) | 165 | 126 | -39 | 290 | -19 | 122.682 | 123.155 |
| 13 | Cached (provider_default) | 180 | 133 | -47 | 165 | -24 | 121.288 | 121.657 |
| 14 | Cached (provider_default) | 213 | 141 | -72 | 376 | -39 | 121.845 | 122.474 |
| 15 | Cached (provider_default) | 163 | 123 | -39 | 271 | -14 | 121.385 | 121.832 |
| 16 | Cached (provider_default) | 172 | 126 | -46 | 503 | -18 | 123.870 | 124.563 |
| 17 | Cached (provider_default) | 175 | 118 | -56 | 148 | -15 | 122.178 | 122.515 |
| 18 | Cached (provider_default) | 171 | 121 | -51 | 137 | -24 | 121.217 | 121.549 |
| 19 | Cached (provider_default) | 171 | 130 | -41 | 139 | -15 | 121.580 | 121.905 |
| 20 | Cached (provider_default) | 166 | 116 | -50 | 162 | -13 | 121.361 | 121.702 |
| 21 | Cold: tensorflow 2.16.1 | 19,564 | 19,542 | -22 | 240 | -14 | 121.508 | 141.326 |
| 22 | Cold: pytorch 2.3.1 cuda | 82,656 | 82,634 | -22 | 206 | -17 | 121.673 | 204.552 |
| 23 | Cold: jupyter datascience | 133,101 | 133,054 | -47 | 430 | -44 | 123.801 | 257.376 |
| 24 | Cold: anaconda3 | 102,487 | 102,466 | -20 | 240 | -15 | 122.908 | 225.650 |
| 25 | Cold: nvidia/cuda devel | 66,068 | 66,049 | -20 | 186 | -16 | 121.208 | 187.479 |

The hourly bill, per App, priced at $0.00012135 per second:

| Case | Bill | Billed seconds | create returned → destroy sent | `createdAt` → `finishedAt` | create sent → destroy returned |
| --- | ---: | ---: | ---: | ---: | ---: |
| Cached x 20 | $0.29190799 | 2,405.5 | 2,436.2 | 2,441.4 | 2,444.3 |
| Cold x 5 | $0.07526144 | 620.2 | 611.1 | 612.5 | 1,016.4 |

A smoke run of 2 sandboxes held 15 s each billed $0.00388244, which is 32.0 s priced, against 33.9 s from create returned to destroy sent: the same direction as the cached batch.

## Verdict

- **Start (supported):** the cold batch's create calls took 20 to 133 s because of the image pull, yet the bill is 620 s against 611 s from create returned and 1,016 s from create sent. The pull was not billed. Billing starts at about the moment Modal's own `created_at` is set. For a cold image that is 20 to 47 ms before the create call returned; for a cached image `created_at` is 129 ms (average) after create sent and 45 ms (average) before create returned. So "create sent" is ruled out for a cold image, and "create returned" fits both cases.
- **End (not settled):** the destroy call takes 0.15 to 0.5 s, which is below the resolution of a batch bill, so destroy sent and destroy returned cannot be told apart. Modal's `finished_at` is 15 to 20 ms before destroy returned in most rows.
- **Not explained:** the cached bill is 1.3% below the shortest edge-based span (30.6 s over 20 sandboxes) and the cold bill is 1.5% above it. The rate above matches Modal's documented rate: the region-selection page applies the multiplier to memory as well as CPU. A start lag of about 1 to 2 s is the remaining candidate.
- **Boundary:** the check is not complete, so the record keeps the boundary unchecked.
- **Reported figure:** Modal's figure is per App per hour. No per-sandbox figure was available to compare with list price.

## Limits

- One account (Starter plan), one region (`us`), one runtime (`gvisor`), one size (2 cores, 4096 MiB); 20 cached and 5 cold sandboxes.
- The cold case used public images; a large private image or one in a different registry was not tried.
- The workspace billing report lists full hours only, so a batch can be read only after its hour ends, and the batch must be isolated in its own App and hour. Modal's billing guide describes these reports for Team and Enterprise plans; the call worked on this Starter workspace.
- Actual CPU and memory use are not reported by Modal. Every figure above prices the request (2 cores, 4096 MiB), which is correct only if the sandbox never used more; the sandboxes here held an idle command, so use above the request is not expected, but it was not measured.
- Modal's raw sandbox list carried `created_at` and, after the sandbox ended, `finished_at`. Start, ready and enqueue times were empty for these sandboxes, while running and after they ended. Other creation options (for example a readiness probe) were not tried.
