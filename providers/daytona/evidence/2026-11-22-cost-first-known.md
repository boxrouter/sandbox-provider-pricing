# How soon a finished sandbox's cost is known

**Date:** 2026-11-22. **Provider:** Daytona. **Result:** On 6 sandboxes that ran 5 to 120 s, 3 had a known cost 312 to 356 s after the destroy call returned (median 342 s); the other 3 stayed unknown for the 1010 s watched. No known figure changed in the 584 to 630 s watched after it first appeared.

## Question

Benchmark trials waited for a sandbox's cost far longer than the provider's records seemed to need:
the first read came at `after_s` and, when it found nothing, the next one a whole `interval_s` later.
How long after a sandbox is destroyed is its cost first known, and does that figure change afterwards?

## Method

- **Sandboxes:** 6 created through BoxRouter's service on one Daytona account used for testing, at 2 vCPU and
  4 GiB asked as a ceiling, each running `true` and then kept alive for a different time (5 to 180 s) before the
  destroy. Each carried the run label `run=lrcost-11220156`.
- **Reads of the provider's records:** a local copy of the service's reaper, scoped to that label, read each
  ended sandbox's provider records on a short schedule: the first read 5 s after the end, then after half the
  sandbox's age (at least 15 s, at most 30 s after the last read once a cost is known). This is the schedule
  `next_read` now gives; it replaces a fixed `interval_s` after the first read.
- **What was timed:** every 5 s a poll of the sandbox's cost record. A cost counted as known at the first
  poll that showed a label other than unknown and a total, measured from destroy returned on the same
  clock. Polling went on after that to see whether the total changed.
- **Limits:** the reads of the provider's records come on the ladder above, so a time is the first poll after
  the first read that found the record: it can lie up to half the sandbox's age after the record arrived.
  The sandboxes ran 6 at a time on a lightly loaded account; a full benchmark run creates hundreds at once,
  which can delay a provider's records. 0 create call(s) failed and are not in the table. The 3 sandboxes that stayed unknown ran 5, 15 and 60 s; the service's read of Daytona's per-sandbox cost ended for them with no record. On 2026-10-24 all 10 rows were readable within 68 s (daytona/evidence/2026-10-24-analytics-row-latency.md), so how soon Daytona's records arrive is not settled; the first read stays at 120 s.
- **Cleanup:** every sandbox was destroyed through the service, and a final sweep by the run label found none.

## Results

Times are seconds. The last column is how long the cost was watched after it first appeared.

| Lifetime | First known | Label | Total (USD) | Changed later | Watched after |
|---|---|---|---|---|---|
| 5 | - | - | - | no | 0 |
| 15 | - | - | - | no | 0 |
| 30 | 356 | reported | 0.0013881386199999998 | no | 630 |
| 60 | - | - | - | no | 0 |
| 90 | 342 | reported | 0.00415399952 | no | 584 |
| 120 | 312 | reported | 0.00553674561 | no | 584 |
