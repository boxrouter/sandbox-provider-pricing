# Settle lag of the per-Sailbox spend record

**Date:** 2026-11-23. **Provider:** Sail. **Result:** The spend figure of each of 16 Sailboxes of 3 to 150 s lifetimes stopped moving 31.7 to 180.3 s after the destroy returned (median 131.5 s); the declared window is 600 s.

## Question

How long after a Sailbox ends does `GET /sailboxes/spend?sailbox_id=` keep changing? The pricing page says only that "Running usage is sampled every second and reported in roughly one-minute batches". The spec needs `limits.cost_final_within_seconds`, a bound after which the figure never changes.

## Method

- Sandboxes: 16 in two rounds of 8 (2026-11-23 08:45Z and 08:50Z), each 1 vCPU, 16 GiB memory limit, 8 GiB disk limit, the Debian base image, labelled with the run id, idle (no workload). Lifetimes after the create returned: round 1: 5, 10, 20, 30, 45, 60, 90, 120 s; round 2: 3, 8, 15, 25, 40, 75, 100, 150 s. All were created at the same moment and each was ended with `POST /sailboxes/{id}/terminate`.
- Reads: one poller read `GET /sailboxes/spend?sailbox_id=<all eight ids>&from=<minute of the first create>` every 5 s (the request answers the per-Sailbox rows of those ids). Sail's rate limit on fleet reads is shared by the whole organization: a first attempt with eight pollers got HTTP 429, `Retry-After: 2` to 5, so one poller was used; 1 and 6 reads of the two rounds were refused and repeated after the stated wait.
- A Sailbox counts as settled at the first read whose `cost_usd_nanos` and `running_seconds` equal every later read, and each was read until both had been unchanged for 60 s after the end. The lag is measured from the moment the terminate returned on our clock; the 5 s read interval and the call's own time are within it.
- Times are ours (the terminate call returned) except the record's own figures, which are Sail's. Sailbox ids are redacted; the series of changes is in `2026-11-23-settle-lag.json`.

## Results

Offsets are seconds after the terminate returned. "First record" is when the Sailbox first had a row (negative: while it still ran). "Settled" is when its figure reached the value it kept. Final running seconds and cost are Sail's own.

| # | Round | Lifetime (s) | Ran, create returned to terminate returned (s) | Create call (s) | First record (s) | Settled (s) | Final running seconds | Final cost (nanos of USD) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 5 | 5.6 | 2.35 | 91.1 | 91.1 | 4.999 | 5410 |
| 2 | 1 | 10 | 10.7 | 2.48 | 65.0 | 159.1 | 9.996 | 11047 |
| 3 | 1 | 20 | 20.6 | 2.66 | 122.9 | 122.9 | 20.005 | 24672 |
| 4 | 1 | 30 | 30.6 | 2.62 | 112.9 | 112.9 | 30.003 | 39228 |
| 5 | 1 | 45 | 45.7 | 3.0 | 60.8 | 165.6 | 44.003 | 56663 |
| 6 | 1 | 60 | 60.6 | 2.39 | 15.2 | 109.3 | 60.023 | 80660 |
| 7 | 1 | 90 | 90.7 | 2.02 | 53.4 | 158.2 | 89.819 | 120092 |
| 8 | 1 | 120 | 120.7 | 2.06 | -44.6 | 149.1 | 119.778 | 159676 |
| 9 | 2 | 3 | 3.8 | 2.36 | 96.7 | 96.7 | 3.002 | 4175 |
| 10 | 2 | 8 | 8.7 | 2.09 | 71.1 | 71.1 | 8.004 | 11826 |
| 11 | 2 | 15 | 15.7 | 3.21 | 31.7 | 31.7 | 15.001 | 18195 |
| 12 | 2 | 25 | 25.6 | 2.21 | 164.0 | 164.0 | 25.0 | 35893 |
| 13 | 2 | 40 | 40.6 | 2.28 | 80.8 | 180.3 | 39.999 | 50974 |
| 14 | 2 | 75 | 75.8 | 2.06 | 25.0 | 140.1 | 73.997 | 97466 |
| 15 | 2 | 100 | 100.8 | 2.57 | 67.6 | 172.3 | 100.002 | 134610 |
| 16 | 2 | 150 | 150.5 | 2.54 | 17.9 | 122.6 | 149.875 | 203623 |

Across the 16: settled at 31.7 s at the earliest, 131.5 s median and 180.3 s at the latest. Eight Sailboxes had a row whose figure was still partial when first read (a batch reported only part of the run) and rose once more or twice before it stopped; the others had their whole figure in the first row. Final running seconds equalled the lifetime in every row to within 0.2 s, except that the create call and the terminate call add about 1 s to the span we timed.

## Verdict

Sail's per-Sailbox figure settled within 180.3 s of the end in every measured Sailbox. `COST_FINAL_WITHIN_S` is 600 s, 3.3 times the longest observed lag, because 16 samples from one organization in 11 minutes do not bound a tail and a wrong `final` is a wrong price. A first read of a Sailbox can be partial, so a figure read before the end plus the declared window is `accruing` and never final.

## Limits

16 Sailboxes, idle, one organization, one region, two 5-minute windows on one day; the devbox clock and the shared rate limit add seconds to each offset. Whether a heavily loaded account or a long-running Sailbox (hours) reports later is not measured. Whether a record can change after it stopped moving for 60 s is not settled (see the open question in `billing.yaml`).
