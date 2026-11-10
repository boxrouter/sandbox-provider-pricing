# How soon a finished sandbox's analytics row arrives

**Date:** 2026-10-24. **Provider:** Daytona. **Result:** On 10 sandboxes that ran 5 to 300 s, each
sandbox's per-sandbox analytics row was readable, covering the sandbox's end, at most 9.4 to 68.2 s
after the destroy call returned. The first row read was already the final one: no row's end or
price changed in the following 20 minutes, and every price equalled list rates × billed seconds.
A read at the sandbox's end finds nothing, so the first read now waits 120 s (`after_s`).

## Question

Cloud reads each ended sandbox's cost from Daytona's analytics API. The revisit policy read first
at the sandbox's end (`after_s: 0`). One live read on 2026-10-24, 5 s after a destroy, answered
that the sandbox had no row yet. The next read then came an hour later. How long after a sandbox
ends does its row arrive, and is that first row already final?

## Method

- **Sandboxes:** 10, created with Daytona's Python SDK (0.220.0) from the default snapshot.
  - Size: 1 vCPU, 1 GiB memory, 3 GiB disk.
  - All ran on one Daytona organization used for testing.
  - Each carried this run's label (`run=dclat-1024-1932`). At most 3 ran at once.
  - Lifetimes, from create returned to destroy sent: 5, 10, 20, 30, 45, 60, 90, 120, 180 and
    300 s.
- **Our times:** create sent and returned, and destroy sent and returned, from our own clock.
- **The provider's figures:** `GET https://analytics.app.daytona.io/organization/{id}/usage/sandbox`
  (`from` two minutes before the first create, `to` now).
  - One request every 15 s answered all 10 sandboxes at once.
  - A sandbox's row counted as arrived at the first answer whose `lastEnd` was at or after our
    destroy sent.
  - After that, every answer was compared with the first. Polling continued until each row had
    been watched for at least 20 minutes.
- **Limits of the polling:** 36 of the 111 requests were refused with HTTP 429. The organization's
  analytics budget is shared with other callers we do not control, and the 429 carries no wait
  hint. A refused request delays when an arrival is seen. Each latency below is therefore an
  upper bound: the row arrived at or before that time.
- **Cleanup:** every sandbox was deleted. A final list by the run label returned none.

## Results

Latency is the first answer that covered the end, minus destroy returned. Billed is Daytona's
`lastEnd − firstStart` (one period each). The list figure uses the 2026-10-11 rates:
$0.000014 per vCPU-second, $0.0000045 per GiB-second of memory and $0.00000003 per GiB-second of
disk, which is $0.00001859 per second at this size.

| # | Lifetime (s) | Create returned → destroy sent (s) | Billed (s) | Destroy returned → row seen (s, upper bound) | Price (USD) | List × billed (USD) | Row changes in 20 min |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 5 | 5.000 | 5.099 | 24.4 | 0.00009479041 | 0.00009479041 | 0 |
| 2 | 10 | 10.000 | 10.132 | 19.4 | 0.00018835388 | 0.00018835388 | 0 |
| 3 | 20 | 20.000 | 20.093 | 9.4 | 0.00037352887 | 0.00037352887 | 0 |
| 4 | 30 | 30.000 | 30.115 | 17.8 | 0.00055983785 | 0.00055983785 | 0 |
| 5 | 45 | 45.000 | 45.186 | 18.7 | 0.00084000774 | 0.00084000774 | 0 |
| 6 | 60 | 60.000 | 60.194 | 68.2 | 0.00111900646 | 0.00111900646 | 0 |
| 7 | 90 | 90.000 | 90.178 | 17.2 | 0.00167640902 | 0.00167640902 | 0 |
| 8 | 120 | 120.000 | 120.127 | 33.2 | 0.00223316093 | 0.00223316093 | 0 |
| 9 | 180 | 180.001 | 180.106 | 21.2 | 0.00334817054 | 0.00334817054 | 0 |
| 10 | 300 | 300.000 | 300.104 | 18.0 | 0.00557893336 | 0.00557893336 | 0 |

- No row appeared before its sandbox ended. Each first appearance already carried the final
  `lastEnd` and price.
- The longest bound, 68.2 s (row 6), fell in a stretch of refused requests. The other nine were
  seen within 34 s.
- Two separate live reads the same day agree:
  - a read 41 s after a 20 s sandbox ended found its row;
  - a read 5 s after another ended found none.

## Verdict

- A finished sandbox's row arrives within about a minute of the destroy call returning: at most
  68.2 s in all 10 cases, and at most 34 s in 9.
- **The revisit's first read is set to 120 s after the end (`after_s: 120`).** That is about 1.75
  times the longest bound measured. A read at the end (`after_s: 0`) finds no row and falls to the
  hourly revisit.
- The first row read was final for at least 20 minutes, and every price was exactly list rates ×
  billed seconds.
  - [2026-10-05](2026-10-05-reported-vs-list-price.md) found first reads 2.73% to 4.25% lower than
    later ones. Nothing like that happened here within 20 minutes.
  - The hourly re-reads until 72 hours stay, because a later change has not been ruled out.

## Limits

- 10 container sandboxes of one size, on one organization and region, during one 30-minute
  window.
- Latencies are upper bounds on a 15 s poll, widened by 429-refused polls. Their true values may be
  lower, but not higher.
- Rows were watched for 20 minutes, not the 72 hours the policy keeps re-reading.
- The analytics endpoint's limits are not documented. Measured the same day: a burst of about 30
  requests, then about 1 a second. The 429 sends no `Retry-After`.
