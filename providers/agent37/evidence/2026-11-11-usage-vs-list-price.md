# Usage report compute against list rates

**Date:** 2026-11-11. **Provider:** Agent37. **Result:** On two default instances, the usage
report's `compute_micros` equalled each instance's billed minutes at the list rates, rounded to a
whole micro-dollar, and was readable 1 s after delete returned. It did not change in the reads
that followed (see Results). How long a total can still change after that, and whether GB means
GiB, are not settled.

## Question

Agent37 publishes monthly rates and says the wallet "is metered per minute (the monthly price
divided by 730 hours, divided by 60)", that "whole minutes are billed at every lifecycle
transition and at least hourly", and that compute "lands [in `GET /v1/usage`] within the hour".
It does not say how a part minute is billed, whether the usage report's per-instance figure is
the list rate applied to those minutes, or how soon a deleted instance's final minutes appear.

## Method

- Instances: two, created with `POST /v1/instances` and no `resources`, which gave the default
  template `agent37-base` (image digest
  `sha256:e1d097ce5d7e75f83d374586baad147d9e7856061bc6920fc08c6506195d0b01`), type `default`,
  region `us`, 2 vCPU, 4 GB RAM, 4 GB disk. The image was cached on Agent37's side; both creates
  returned `201` with `status: running` in under a second.
- What we did: instance A ran until it was deleted. Instance B ran for five minutes, was stopped
  (`POST /v1/instances/{id}/stop`) and stayed stopped until it was deleted at the same time as A.
  Before the deletes we read each instance's start and sleep history
  (`GET /v1/instances/{id}/events`). Calls were made with Python's standard HTTP client against
  `https://api.agent37.com/v1`.
- Our times: every call's send and return on our clock (UTC), below.
- The provider's figures: `GET /v1/usage?from=2026-11-11&to=2026-11-11`, read before the
  creates, 1 s after the deletes returned, and then every five minutes through the adapter's own
  cost reader (`adapter-agent37` 0.1.1, `provider_reports.aread_cost`), which reports a total once
  the instance is deleted and the same total has held for an hour. Integer micro-dollars;
  nothing converted.
- List rates (price version `agent37@2026-11-11`): $0.80 per vCPU-month, $0.70 per GB-month of
  RAM, $0.09 per GB-month of disk; a month is 730 hours, so a minute is 1/43,800 of a month.
  For this size, a running minute is (2 × 0.80 + 4 × 0.70 + 4 × 0.09) / 43,800 = $4.76 / 43,800
  = 108.6758 micro-dollars, and a stopped minute is $0.36 / 43,800 = 8.2192 micro-dollars.

Our calls (UTC):

| Call | Sent | Returned |
| --- | --- | --- |
| Create A (`u4q5psdda1`) | 20:46:33.595 | 20:46:34.531 |
| Create B (`yof8skq3ow`) | 20:46:34.531 | 20:46:35.264 |
| Stop B | 20:51:35.265 | 20:51:35.753 (answer `status: stopped`) |
| Delete A | 20:58:37.373 | 20:58:37.781 |
| Delete B | 20:58:37.781 | 20:58:38.235 |
| Usage | 20:58:38.752 | 20:58:39.086 |

Both instances' `created` was 20:46:34 (epoch 1794429994). Agent37's history for A was one
`instance.started` at 20:46:34; for B, `instance.started` at 20:46:35 and `instance.stopped` at
20:52:35, a minute after the stop returned, on the billed minute as the billing page says
("Each time falls on the billed minute, up to a minute after the change itself").

## Results

| Instance | Life (create returned to delete sent) | `awake_minutes` | Billed minutes | List price (micro-dollars) | `compute_micros` | `total_micros` |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| A | 12 min 2.8 s | 13 | 13 running | 13 × 108.6758 = 1412.79 | 1413 | 1413 |
| B | 12 min 2.5 s | 6 | 6 running + 7 stopped | 6 × 108.6758 + 7 × 8.2192 = 709.59 | 710 | 710 |

- A's 12 minutes 3 seconds were billed as 13 minutes: the part minute before the delete was billed
  in full.
- B ran 5 minutes 0.5 s before the stop, which was billed as 6 running minutes (its history puts
  the stop at 20:52:35, the end of the sixth minute). Its stopped time from there to the delete,
  6 minutes 3 s, was billed as 7 disk-only minutes. Each period was rounded up to whole minutes,
  and the next state began where the billed minutes ended, so the whole life was 13 minutes, as
  for A.
- Rounding each settled debit to a whole micro-dollar fits both: 652.05 → 652 for B's running
  minutes and 57.53 → 58 for its stopped minutes give 710. Rounding each debit up would give 711.
- Both totals were in the usage report 1 s after delete returned. The adapter's reads every five
  minutes from 20:58:53 returned the same totals: 13 reads to 21:59:02,
  all 1413 and 710. The 13th, an hour after the first, reported both as settled (`available`),
  which is the reading the fixtures `best` (A) and `stopped` (B) record.
- Neither instance had managed-service spend: `llm_micros`, `brave_micros`, `composio_micros` and
  `perflo_micros` were 0, so `total_micros` equalled `compute_micros`.

## Verdict

Agent37's per-instance `compute_micros` is the list price of the instance's billed minutes, to the
micro-dollar, for a running instance and for one that was stopped part way. It is labelled
`reported`. A deleted instance's final minutes are in the usage report at once, well inside the
hour the billing page allows.

This does not settle how long a deleted instance's total can still change (the reads cover the
window above), whether rates on a discounted account are reported at list, or whether GB means
GiB: the report prices the size as Agent37 states it (4 GB), so this check cannot tell them apart.

## Limits

Two instances of one size, the default type and template, region `us`, one list-rate account, one
day. Performance and VM instances, sleeping and waking, cold storage and instances that span a
UTC day boundary or an hourly settlement were not measured.
