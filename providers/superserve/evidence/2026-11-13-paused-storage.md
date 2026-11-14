# Storage on a paused Superserve sandbox

**Date:** 2026-11-13. **Provider:** Superserve (one BoxRouter team, legacy
pay-as-you-go catalog). **Result:** One sandbox with 1 GiB of random data written, paused for 11 min 18 s, was billed
nothing for storage. The team's meter and charges stayed at 0 for storage (`storage_mib_seconds` 0, `storage_gib_hours` 0,
`cost_breakdown_usd.storage` 0), and the team's hourly series marked storage `billable: false` with `cost_usd` 0. The same
series did record storage usage for this sandbox, 2,414.76 GiB-seconds, which grew while the sandbox was paused. Superserve
documents that storage "remains tracked-only". Compute and memory were billed for the 60.49 s the sandbox ran: $0.002783,
which the team's hourly bucket and the list rates agree on.

## Question

Does Superserve bill for the storage of a sandbox that stays paused? The pricing page says storage is billed "for as long as
you keep it" (shared template once, plus retained sandbox changes) at $0.000108 per GiB-hour, while the public pricing data
(`GET /billing/pricing/public`) lists storage with `"billable": false`. The earlier check
([billing boundary](2026-11-13-billing-boundary.md)) saw `storage_mib_seconds` 0 on six sandboxes of 30 to 90 s, none paused
for long.

## Method

- **One sandbox**, created through the Python SDK 0.12.0 on the default template `superserve/base` (2 vCPU / 4096 MiB, 8 GiB
  root disk), `timeout_seconds` 120, `auto_delete_seconds` 720, metadata `run=ss-storage-20261113T121730Z`. These two limits
  bound its life to about 860 s even if the script died. Script: `run.py` (key from Secrets Manager, never printed or
  written).
- **Data written:** `dd if=/dev/urandom of=/home/user/blob.bin bs=1M count=1024 conv=fsync` (1,073,741,824 bytes, 3.39 s),
  then `sync`. The root disk's used space went from 1,708 MiB to 2,732 MiB (`df`).
- **Pause** by us at 60.3 s after the create call returned (`POST /pause`, waited for completion); the sandbox stayed paused
  until we deleted it.
- **Readings:** at the pause and 3, 6, 9 and 11 minutes after it, plus 15 s after the 11-minute reading and 8 s after the delete.
  Each reading saved the team's cumulative usage (`GET /teams/{id}/billing/usage`), the hourly usage series
  (`GET /billing/usage-series`, hour buckets, UTC, storage field included), `GET /billing/summary`, the sandbox's own state, the
  sandbox list by label, and `GET /activity` since 60 s before the run. A watcher also read `/activity` every 2 s (355 polls, no
  errors). Raw answers: `raw/` (one file per reading; `access_token` and `routing_hint` removed).
- **Delete** with `kill_by_id` after the 11-minute reading and its 15 s repeat, before `auto_delete_seconds` would have acted
  (`auto_delete_at` 12:30:34).
- **Attribution.** `GET /sandboxes` was empty before the run and after it. The audit log held three sandbox rows from 60 s
  before the create to 8 s after the delete, all this sandbox's. No other lane's sandbox ran in the window, so every
  team-wide figure below is this sandbox's.

## Results

### Lifecycle rows (`GET /activity`)

| row | time UTC | first seen by the watcher |
| --- | --- | --- |
| `started` | 12:17:33.207 | 12:17:33.651 |
| `paused` | 12:18:34.453 | 12:18:35.031 |
| `deleted` | 12:29:52.986 | 12:29:54.246 |

Running period: 61.246 s from the rows. Paused: 678.5 s (11 min 18.5 s) until the delete, 12 min 20 s from create to delete.

### What the team's sources showed at each reading

| reading (UTC) | sandbox state | `storage_mib_seconds` (team meter) | storage usage, series bucket 12:00 (GiB-seconds) | storage `cost_usd` | summary `cost_breakdown_usd.storage` |
| --- | --- | ---: | ---: | ---: | ---: |
| 12:17:31 before create | none | 0 | 0 | 0 | 0 |
| 12:18:34 at the pause | paused | 0 | 546.541 | 0 | 0 |
| 12:21:34 (+3 min) | paused | 0 | 1,862.234 | 0 | 0 |
| 12:24:34 (+6 min) | paused | 0 | 1,862.234 | 0 | 0 |
| 12:27:34 (+9 min) | paused | 0 | 2,414.760 | 0 | 0 |
| 12:29:34 (+11 min) | paused | 0 | 2,414.760 | 0 | 0 |
| 12:29:51 (+11 min 17 s) | paused | 0 | 2,414.760 | 0 | 0 |
| 12:30:00 after delete | gone (404) | 0 | 2,414.760 | 0 | 0 |

- Every other storage field stayed 0 as well: `storage_gib_hours`, and the `storage_gib` entry of `resources` (`tracked: true`,
  `billable: false`).
- The series' storage usage is the only storage figure that moved. It rose in steps (four of the seven readings after the first repeated the
  previous value) and did not change after the sandbox was deleted. Its unit is "tracked storage GiB-seconds" in
  Superserve's OpenAPI. The figures do not follow from the 8 GiB disk or the 1 GiB written (546.5 GiB-s after a 61 s run; 2,414.8
  GiB-s over 740 s of life), and this check cannot say what the meter counts.
- Had the series' storage usage been priced at the listed $0.00000003 per GiB-second ($0.000108 per GiB-hour) it would be
  $0.0000724; Superserve's own `cost_usd` for it is 0.

### Compute and memory for the same run

| | value |
| --- | ---: |
| Team `vcpu_seconds` delta, before to after | 120.98166 (60.49083 s on 2 vCPUs) |
| Team `memory_mib_seconds` delta | 247,770.43968 (60.49083 s at 4096 MiB) |
| Series bucket 12:00 | cpu 120.98166 vCPU-s, $0.00169374; memory 241.96332 GiB-s, $0.00108883 |
| `billed_total_usd` (bucket 12:00) | **$0.00278258** |
| `current_charges_usd`, before to after | 0.392411819 to 0.395194397: **+$0.00278258** |
| List rates × 60.49083 s × (2 vCPU, 4 GiB) | $0.00278258 |
| List rates × 61.246 s from the `started` and `paused` rows | $0.00281732 |

The charge rose by exactly the compute and memory cost. Storage added no charge, over the 678.5 s the sandbox spent paused or
at any reading. The meter ran 0.755 s less than the rows, more than the 0.09 to 0.38 s seen in the earlier check; this check
does not explain the difference. Cost of the run: **$0.002783**.

### Cleanup

- `GET /sandboxes?metadata.run=ss-storage-20261113T121730Z` with every non-deleted status: 0 sandboxes (`raw/cleanup-by-label.json`);
  with no status filter: 0 (`raw/cleanup-by-label-any-status.json`); `GET /sandboxes` for the team: 0.
- The paused sandbox's snapshot `442ad7ab-5593-4e95-b420-a44a351becdf`: `GET /snapshots/{id}` answers 404 after the delete.
  `GET /sandboxes/{id}`: 404. (`raw/after-snapshot-check.json`)

## Verdict

- **Measured: storage billed 0 for a sandbox paused 11 min 18 s (12 min 20 s of life) with 1 GiB of incompressible data written.**
  Team charges rose only by compute and memory, and every storage price or charge field was 0.
- This agrees with Superserve's public pricing data (storage `billable: false`) and OpenAPI text (storage "tracked-only" and
  excluded from `billed_total_usd`), and contradicts the pricing page's "billed for as long as you keep it". It does not show
  whether storage will be billed later, or for longer pauses.
- The team's hourly series does track storage usage for this sandbox, and it grew while paused. A change from tracked-only to
  billed would show as `billable: true` and a nonzero `cost_usd` in that series, so those two fields are the signal to watch.
- Calculated cost for a paused sandbox stays compute and memory for its running periods only, as in the billing-boundary check.

## Limits

- One sandbox, one team, one region, one pause of 11 min 18 s. Longer pauses (hours, days) are not tested; a storage meter that
  starts after 12 minutes, or a charge that appears at a daily or monthly settlement, would not show here.
- The team's `current_charges_usd` is a running figure. A billing period closes on 2026-11-23, and the invoice was not read.
- The disk was 8 GiB with 2.7 GiB used. A larger retained diff, a sandbox from a custom template, or a snapshot taken by
  `POST /snapshots` was not tested.
- The unit and basis of the series' storage usage are not established here.
- Rows and meter differ by 0.755 s for this single running period.
