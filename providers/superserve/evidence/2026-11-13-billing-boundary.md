# Billing boundary against Superserve lifecycle rows

**Date:** 2026-11-13. **Provider:** Superserve (one team, legacy
pay-as-you-go catalog). **Result:** On six sandboxes (seven billed periods) in a window where no other sandbox ran,
the `started` row of Superserve's audit log (`GET /activity`) fell inside each create call and the `deleted` row inside
each destroy call. Pricing each period from those rows (`started` to the next `paused`, `timeout_paused` or `deleted`, minus
paused time) at the list rates came to $0.014587, against $0.014529 in the team's hourly usage series: 0.400% above. The
rows over-count by 0.09 to 0.37 s per period, so the calculation is an upper bound that is exact to about 0.2 s per
period. Superserve reports no per-sandbox cost or usage record.

## Question

Which provider timestamps start and end billing for one sandbox, and can a sandbox's cost be calculated from them? Superserve
documents billing only per team (`/billing/usage-series`, `/billing/summary`, `/teams/{id}/billing/usage`), so the check
prices each sandbox from its audit-log rows and compares the sum with the team's own meter.

## Method

- **Quiet window.** Before the first create, `GET /sandboxes` was empty on three checks 20 s apart and no sandbox row had
  appeared in the audit log for the previous 60 s. A watcher read `GET /activity?start=...` every 0.5 s from 30 s before the
  first create to the end (995 polls in the first run, no errors). Every sandbox row it saw in the 09:12 to 09:30 UTC window
  was one of ours (16 rows). Another run on the same team made 32 short sandboxes from 09:01:34 to 09:01:50, which
  is before this window; the hourly bucket read at 09:12:55 already includes them and is the baseline.
- **Sandboxes:** six, each at most 300 s, created through the Python SDK 0.12.0 on team template `superserve/base`
  (2 vCPU / 4096 MiB, `timeout_seconds` 300) unless the table says otherwise; each carried a run label in its metadata.

  | key | what we did |
  | --- | --- |
  | `plain30` | busy loop 30 s, then destroy |
  | `plain90` | busy loop 90 s, then destroy |
  | `timeout45` | `timeout_seconds` 45, `auto_delete_seconds` 0, busy loop; never destroyed by us |
  | `small45` | existing team template `boxrouter-img-std-76dd55eacf6ea4a7` (2 vCPU / 2048 MiB), busy 45 s, destroy |
  | `pauseresume` | `auto_delete_seconds` 0, busy 30 s, `POST /pause`, wait 30 s, `POST /resume` (failed: see Results) |
  | `pauseresume2` | `auto_delete_seconds` unset, busy 30 s, pause, wait 30 s, resume, busy 30 s, destroy |

  The busy command is `timeout N sh -c 'while :; do :; done'`. The 2048 MiB template was already in the team; we used it and
  did not create or delete a template.
- **Our times:** for each call, the moment it was sent and returned, from the local clock. A Date-header comparison at the
  start of the run (three samples) put Superserve's clock 0.005 to 0.106 s ahead of ours.
- **The provider's figures:** every audit-log row for the sandbox (`action`, `created_at`, `duration_ms`), read by the watcher,
  and the team's cumulative `GET /teams/{id}/billing/usage` (`vcpu_seconds`, `memory_mib_seconds`; 1e-6 resolution) read
  before the create and 5 s after the final row, so each case has its own meter delta. The team's `/billing/usage-series` hourly
  bucket was read at 09:12:55 (before) and 09:29:54 (after).
- **Computed cost:** active seconds × (vCPUs × $0.000014 + GiB of memory × $0.0000045). Active seconds are the sum of
  `started`/`resumed` to the next `paused`, `timeout_paused` or `deleted`.
- **Event lag:** the time between a row's own `created_at` and the first poll that returned it, 16 rows.
- **Retention:** the audit log was paged to its oldest row.

## Results

### Rows against our call times (milliseconds; negative = row before the call returned)

| key | `started` - create sent | `started` - create returned | end row | end - destroy sent | end - destroy returned |
| --- | ---: | ---: | --- | ---: | ---: |
| `plain30` | 276.8 | -33.2 | `deleted` | 574.2 | -49.8 |
| `plain90` | 343.0 | -241.0 | `deleted` | 302.8 | -5.2 |
| `small45` | 238.0 | 3.0 | `deleted` | 302.3 | 4.3 |
| `pauseresume2` | 287.5 | -41.5 | `deleted` | 379.1 | -39.9 |
| `timeout45` | 498.8 | -2.2 | `timeout_paused`, then `auto_deleted` 242 ms later | not our call | not our call |
| `pauseresume` | 311.8 | -7.2 | `paused` | pause sent +441.6 | pause returned +18.6 |

`started` fell after create was sent and within 3.0 ms of create returning or earlier on all six; `deleted` fell
after destroy was sent and within 4.3 ms of it returning or earlier on all four destroys. `pauseresume2`'s `paused` row came 470.0 ms after
pause was sent and 45.0 ms after it returned; its `resumed` row 349.7 ms after resume was sent and 12.7 ms after it returned.

### Audit-log rows and billed seconds per sandbox

| key | rows (action, time UTC) | active s from rows | provider meter s | rows - meter |
| --- | --- | ---: | ---: | ---: |
| `plain30` | started 09:13:55.566; deleted 09:14:26.771 | 31.205 | 31.107 | +0.099 |
| `plain90` | started 09:14:34.362; deleted 09:16:05.386 | 91.024 | 90.932 | +0.092 |
| `timeout45` | started 09:16:12.853; timeout_paused 09:17:18.282; auto_deleted 09:17:18.524 | 65.429 | 65.062 | +0.367 |
| `small45` (2 vCPU / 2048 MiB) | started 09:17:26.674; deleted 09:18:12.477 | 45.803 | 45.697 | +0.107 |
| `pauseresume` | started 09:18:19.680; paused 09:18:50.702; auto_deleted 09:18:58.342 | 31.022 (to paused) | 30.781 | +0.241 |
| `pauseresume2` | started 09:25:42.755; paused 09:26:13.532; resumed 09:26:44.488; deleted 09:27:15.306 | 61.596 (30.777 + 30.818) | 61.217 | +0.379 |

"Provider meter s" is the case's own team-usage delta (`vcpu_seconds` ÷ vCPUs; `memory_mib_seconds` ÷ MiB gives the same
number to six places). `duration_ms` was null on every row. No row carries a size or a cost; the size is the sandbox's own
`vcpu_count` and `memory_mib` from `GET /sandboxes/{id}` while it exists.

### Cost, sum against the team's hourly series

| key | computed cost (USD) |
| --- | ---: |
| `plain30` | 0.001435452 |
| `plain90` | 0.004187094 |
| `timeout45` | 0.003009721 |
| `small45` | 0.001694723 |
| `pauseresume` | 0.001427001 |
| `pauseresume2` | 0.002833408 |
| **sum** | **0.014587400** |

- The team's 09:00 hourly bucket (`billed_total_usd`) rose from 0.001383488 (09:12:55) to 0.015912779 (09:29:54): **0.014529291**.
- The computed sum is **0.000058 (0.400%) above** it. CPU usage in the bucket rose 649.590 vCPU-s against 652.158 computed
  (-2.568); memory rose 1,207.786 GiB-s against 1,212.708 computed (-4.922). The difference is 1.28 s of vCPU-time over seven
  periods, 0.18 s per period.
- Pricing each case's own meter delta at list rates gives $0.013113 for the five cases other than the failed first pause/resume;
  computed from rows those five are $0.013160 (0.359% above).
- The meter is 0.09 to 0.11 s shorter than the rows on every period that ends in `deleted`, and 0.24 to 0.37 s shorter on every
  period that ends in a pause (`paused`, `timeout_paused`). These rows cannot say whether the meter starts later, ends earlier, or both.
- **Not exact:** an upper bound by 0.4% here. The window was quiet by the rows above, so the delta is the sandboxes' own.

### What ended each sandbox

- **Destroy:** `deleted` row, in the destroy call.
- **Own timeout:** `timeout_seconds` was 45 s. The `timeout_paused` row came 65.429 s after `started`, **20.43 s late**, and an
  `auto_deleted` row followed 242 ms later (`auto_delete_seconds` 0). No `deleted` row exists. The meter stopped at 65.062 s,
  0.367 s before `timeout_paused` and 0.609 s before `auto_deleted`, so billing ends at `timeout_paused`, not at
  `auto_deleted`. This repeats the 20 s lateness seen on the lifetime test of 2026-11-13 (60 s lifetime, gone at 82.7 s).
- **Pause with `auto_delete_seconds` 0:** the first `pauseresume` run was deleted 7.64 s after its `paused` row by an
  `auto_deleted` row (the window for the paused state is 0 s), so the 30 s wait ended in `404` on resume. The meter counted
  30.781 s: the paused 7.64 s was not billed. The case was rerun with `auto_delete_seconds` unset.
- **Pause then resume:** `paused` and `resumed` rows bracket the paused period (09:26:13.532 to 09:26:44.488, 30.956 s). That
  period added nothing to the meter, which counted only the two active periods (61.217 s). Storage usage (`storage_mib_seconds`)
  stayed 0 in every case. The resumed sandbox kept its id.

### Event lag (separate from billing)

The first poll (every 0.5 s) returned each row 0.040 to 0.771 s after its own `created_at` (16 rows):

| row | lag s (first seen minus row time) |
| --- | --- |
| `paused` | 0.040, 0.455 |
| `resumed` | 0.295 |
| `started` | 0.311, 0.348, 0.373, 0.395, 0.526, 0.540 |
| `deleted` | 0.273, 0.421, 0.581, 0.737 |
| `auto_deleted` | 0.273, 0.529 |
| `timeout_paused` | 0.771 |

Lag includes the poll interval (up to 0.5 s) and Superserve's clock being up to 0.1 s ahead. Every row was first seen within 0.771 s of its own
time, and the watcher kept polling to the end of the run without a row appearing late.

### Retention

The audit log held 1,615 rows when paged on 2026-11-13, back to the first row, a `started` at 2026-10-23T17:57:38Z, the
team's first sandbox: 21 days old and not expired. `GET /activity` without `limit` returns only the newest 200 rows, so a
reader must page with `limit` and `offset` or narrow with `start`/`end` and `q`. A deleted sandbox disappears from every other
endpoint: `GET /sandboxes/{id}` and `/sandboxes/{id}/network` answer 404, and `GET /sandboxes?status=deleted` is empty.

## Verdict

- Superserve's `started` and `deleted` rows land in the create and destroy calls, and the rows and the meter agree to
  0.09 to 0.38 s per period (0.1% to 0.6% of a 30 to 90 s sandbox). This supports using the provider's own row timestamps as
  the billing clock for a **calculated** cost, with the list rates and the sandbox's own size.
- A sandbox that ends by its own timeout has no `deleted` row; the end is `timeout_paused` (billing stops there; `auto_deleted`
  follows). A paused sandbox needs `paused` and `resumed` rows. A cost needs an end row of one of `paused`, `timeout_paused`,
  `deleted` or `auto_deleted`; with none, the cost is unknown.
- It is not a provider-reported cost: no per-sandbox cost or usage exists, so the check cannot show how Superserve rounds,
  and the 0.4% excess is unexplained.
- Not settled: whether the `started` row or an earlier moment starts the meter; whether `memory_current_mib` (live memory
  resizing) changes the memory billed; rows for idle-timeout pauses, `failed` and `migrating` states; any account-specific rate;
  how long the audit log keeps rows beyond 21 days; whether storage is ever billed.

## Limits

- Six sandboxes of 30 to 90 s in the window 09:13 to 09:28 UTC, one team, one region (`use`), the legacy Free catalog with
  $100 credit; one 2048 MiB case and one pause/resume case.
- Rows were read with a 0.5 s watcher, not a distribution of the lag.
- Superserve's clock was ahead of ours by up to about 0.1 s in this window; an earlier part-1 run (08:10) showed rows 0.87 s after our
  call times, so absolute offsets from other times are not comparable; durations between two provider rows are.
- The hourly series gives dollars only to 1e-9 and only for the whole team; this comparison holds only because no other run ran
  between the two readings (rows prove it).
