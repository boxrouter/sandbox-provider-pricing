# How soon a finished sandbox's cost is known

**Date:** 2026-11-22. **Provider:** Vercel. **Result:** On 5 sandboxes that ran 5 to 90 s, 5 had a known cost 5 to 85 s after the destroy call returned (median 60 s). No known figure changed in the 893 to 898 s watched after it first appeared.

## Question

Benchmark trials waited for a sandbox's cost far longer than the provider's records seemed to need:
the first read came at `after_s` and, when it found nothing, the next one a whole `interval_s` later.
How long after a sandbox is destroyed is its cost first known, and does that figure change afterwards?

## Method

- **Sandboxes:** 5 created through BoxRouter's service on one Vercel account used for testing, at 2 vCPU and
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
  The sandboxes ran 5 at a time on a lightly loaded account; a full benchmark run creates hundreds at once,
  which can delay a provider's records. 0 create call(s) failed and are not in the table.
- **Cleanup:** every sandbox was destroyed through the service, and a final sweep by the run label found none.

## Results

Times are seconds. The last column is how long the cost was watched after it first appeared.

| Lifetime | First known | Label | Total (USD) | Changed later | Watched after |
|---|---|---|---|---|---|
| 5 | 85 | calculated | 0.000216091222222222222222222222222222222222222222222222222222222 | no | 898 |
| 15 | 75 | calculated | 0.000454337011111111111111111111111111111111111111111111111111111 | no | 898 |
| 30 | 60 | calculated | 0.000771367622222222222222222222222222222222222222222222222222223 | no | 898 |
| 60 | 31 | calculated | 0.00153177490555555555555555555555555555555555555555555555555555 | no | 898 |
| 90 | 5 | calculated | 0.0022979822611111111111111111111111111111111111111111111111111 | no | 893 |
