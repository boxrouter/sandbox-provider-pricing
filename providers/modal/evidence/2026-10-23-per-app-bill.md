# Per-sandbox cost through one Modal App per sandbox

**Date:** 2026-10-24 (UTC; the run began 2026-10-24 01:41 UTC, the evening of 2026-10-23 in US Eastern). **Provider:** Modal. **Result:** with one App per sandbox, Modal's hourly per-App bill covers exactly one sandbox, and its cost is 2.22 s (median) below Modal's own `created_at` to `finished_at` priced at the list rate, on all 325 sandboxes. Rows appear while the hour is still open. The 200 deployed-App limit is real; stopping an App releases it. How long Modal keeps rows is not known.

## Question

Modal reports cost per App per hour, never per sandbox. If every sandbox runs in its own App, does the App's hourly bill row equal that one sandbox's cost? Does it hold at benchmark scale (6 concurrent), after the App is stopped, across an hour boundary, and how soon do the rows appear and settle?

## Method

- **Workspace:** `boxrouter-internal`, environment `main`. Token read from AWS Secrets Manager; never printed.
- **Sandboxes:** 325 in total, each with `cpu=(2,2)`, `memory=(4096,4096)`, region `us`, runtime `gvisor`, Modal's default image, a `sleep infinity` entrypoint, and a trivial `exec echo` every 10 s while held. SDK 1.6.0, six at a time. Each in its own App named `bench-cost-ma1024-<n>`.
  - **Batch 1:** 25 sandboxes held 120 s; Apps stopped as soon as the sandbox ended; 5 of the 25 used a temporary App (`app.run()`), the rest `App.lookup(create_if_missing=True)`.
  - **Batch 2:** 300 attempted, held 60 s, `App.lookup` Apps left deployed (every tenth a temporary App). 82 failed with `Deployment failed: reached limit of 200 deployed apps` (no sandbox started; no 429s). I stopped all my Apps and ran those 82 again as batch 3 (numbered 301 to 382), each App stopped as soon as its sandbox ended.
  - Final: 290 `App.lookup` Apps and 35 temporary Apps, 218 + 25 + 82 sandboxes in batches 2, 1, 3.
- **Our times:** for every call, sent and returned, from our own clock.
- **Modal's figures:** `created_at`, `started_at`, `enqueued_at`, `finished_at` from the sandbox list with finished sandboxes included (read right after terminate). The bill: `modal.Workspace.billing.report(resolution="h")`, read every 5 minutes from 01:41 to 03:42 UTC and once at 04:05 UTC (26 reads, raw rows kept with read time).
- **Expected cost:** (`finished_at` − `created_at`) × $0.00012135 per second (1.15 × (2 × $0.00003942 + 4 × $0.00000667), the `us` multiplier).
- Raw reads and per-sandbox analysis are retained by the maintainers; the reproducible analysis script and outputs accompany the evidence.

## Results

**One App, one row per hour, one sandbox.** All 325 Apps have a bill row (331 rows: 319 Apps with one row, 6 with two for the hour boundary). No row belongs to a sandbox that is not ours.

| Set | Sandboxes | Billed seconds, median | `created_at`→`finished_at`, median | Bill − expected, median | Bill − expected, max absolute | Bill − expected, % median |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| All | 325 | n/a | n/a | -2.221 s | 3.327 s | -3.68% (60 s) / -1.86% (120 s) |
| Batch 1 (120 s) | 25 | 117.976 | 120.215 | -2.238 s | 2.487 s | -1.86% |
| Batch 2 (60 s) | 218 | 57.988 | 60.209 | -2.221 s | 3.327 s | -3.69% |
| Batch 3 (60 s) | 82 | 57.988 | 60.207 | -2.219 s | 2.516 s | -3.69% |
| `App.lookup` Apps | 290 | n/a | n/a | -2.221 s | 3.327 s | -3.69% |
| Temporary Apps | 35 | n/a | n/a | -2.220 s | 2.424 s | -3.67% |

Every difference is negative (range -3.33 s to -2.16 s). Total billed $2.4690 against $2.5582 expected. Against `started_at`→`finished_at` the bill is 1.85 s lower (median; range -3.02 s to -1.01 s).

**Hour boundary (6 sandboxes, #49 to #54, 02:00 UTC):**

| # | Billed seconds 01:00 row | Billed seconds 02:00 row | Sum − expected |
| ---: | ---: | ---: | ---: |
| 49 | 22.0 | 36.0 | -2.25 s |
| 50 | 22.0 | 36.0 | -2.21 s |
| 51 | 22.0 | 36.0 | -2.23 s |
| 52 | 20.0 | 38.0 | -2.26 s |
| 53 | 20.0 | 38.0 | -2.20 s |
| 54 | 20.0 | 38.0 | -2.20 s |

Each pair sums to the same shortfall as a sandbox inside one hour (-2.2 s). The split between the two rows is in whole seconds and differs from a split at the boundary of `created_at`/`finished_at` by 0.7 to 1.8 s for the first hour (the boundary split is not exactly reproducible).

**Modal scheduling offsets (seconds, 325 sandboxes, from Modal's list and our clock):**

| Offset | Median | p95 | Min | Max |
| --- | ---: | ---: | ---: | ---: |
| `started_at` − `created_at` | 0.407 | 0.517 | 0.184 | 1.194 |
| `enqueued_at` − `created_at` | 0.000 | 0.000 | 0.000 | 0.000 |
| `created_at` − create sent | 0.045 | 0.122 | 0.025 | 0.189 |
| `created_at` − create returned | -0.021 | -0.016 | -0.060 | -0.014 |
| `finished_at` − destroy sent | 0.189 | 0.400 | 0.129 | 1.295 |
| `finished_at` − destroy returned | -0.017 | -0.013 | -0.058 | -0.011 |

Create call 65 ms median (p95 140, max 243); destroy call 206 ms median (p95 444, max 1,314); App creation 169 ms median (p95 248, max 2,484) for `App.lookup` and temporary Apps together. No 429s and no other errors.

**Rows against the hour.**

| Measure | Median | p95 | Min | Max |
| --- | ---: | ---: | ---: | ---: |
| First read showing a row, minus `created_at` (s) | 241 | 364 | 59 | 372 |
| First read showing the row's final value, minus the sandbox's end inside that hour (s) | 187 | 313 | 59 | 315 |
| First read showing the final value, minus the hour's close (s) | -1,685 | 105 | -3,495 | 105 |

Reads were 5 minutes apart, so each figure carries up to 300 s of resolution. Rows appear and grow while the hour is open, usually within 1 to 6 minutes of the sandbox ending; they do not wait for the hour to close. The only rows whose final value came after the hour's close are the first-hour rows of the 6 boundary sandboxes, final within 105 s of 02:00 (the sandbox ended after the close). 35 of 331 rows changed value between reads, all while their sandbox was still running or in the first read after it ended; no row changed value more than 60 s after its hour closed (0 of 331), including between the 03:42 read and the 04:05 read, 2 h 5 min after the 02:00 hour closed and 1 h 5 min after the 03:00 hour closed.

**Stopped Apps.** Batch 1 and batch 3 Apps (107 sandboxes) were stopped immediately after the sandbox ended, and the 35 temporary Apps exited at the end of their `app.run()`; all their rows were present and unchanged. Batch 2's 218 sandboxes had their Apps stopped about 2 minutes after the batch ended (after the failures), and their rows were unaffected.

**Limit.** The workspace refused new deployed Apps at 200 (`Deployment failed: reached limit of 200 deployed apps`; "Please upgrade your workspace plan"), at the 209th sandbox of batch 2 with about 190 of my `App.lookup` Apps still deployed. The 35 temporary Apps never failed, but whether they count toward the 200 was not tested. Stopped Apps release the allowance (batch 3 ran 82 more). Listing Apps in the environment after stopping all 325 returned 50 of mine (62 for the whole environment), so the App list does not show every stopped App; the bill still named all 325.

## Verdict

- **Per-App row = one sandbox's cost (supported):** 325 of 325, one row per App and hour, no other sandbox in any row.
- **Level of the bill (supported):** the row is below the price of `created_at`→`finished_at` by 2.22 s median (max 3.33 s) for every sandbox, a fixed amount that is larger in percent for short sandboxes (3.7% at 60 s, 1.9% at 120 s). The bill is not equal to the span priced at the list rate; use the bill, not the span.
- **Canonical end against hour close:** the sandbox's end (`finished_at`) is when its cost stops growing. The close of the hour is not when the row appears or settles: rows were readable before the hour closed and changed only until about 2 minutes after the sandbox's end (the boundary rows: within 105 s of the close). A benchmark can read its bill after its last sandbox ended and a few minutes, without waiting for the hour to close; whether Modal revises rows later is covered only up to 2 h 5 min.
- **Hour boundary (supported for 6 sandboxes):** two rows, summing to the same bill as a sandbox in one hour.
- **Stopped App (supported):** rows readable and unchanged.
- **Retention unknown:** the oldest row read was about 2.5 hours after its sandbox (01:41 sandbox, read at 04:05). How long Modal keeps rows, and whether it adjusts them later, was not tested.
- **Limit (supported):** 200 deployed Apps per workspace on this plan; plan on stopping each App after its sandbox, or using a temporary App.

## Limits

- One workspace (`boxrouter-internal`, environment `main`), one region (`us`), one runtime (`gvisor`), one size (2 cores, 4096 MiB), the default image only; 60 s and 120 s holds, an idle command plus `echo` calls. Actual use above the request was not measured.
- Only whole-App rows were read; nothing Modal reports per sandbox exists to compare with, so the -2.2 s is against Modal's own `created_at`/`finished_at`, not an independent per-sandbox figure.
- The 5-minute read interval limits the lag figures to that resolution.
- 6 boundary sandboxes, all around one hour boundary (02:00 UTC).
- The shortfall could be a start offset, an end offset or per-second rounding; the whole-second split of the boundary rows suggests the bill is kept in whole seconds. Not settled.
- Other workloads in the workspace may share the 200-App allowance; the exact count at the failure was not recorded.
