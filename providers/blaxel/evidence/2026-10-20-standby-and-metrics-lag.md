# Time to standby and metrics lag against per-sandbox metrics

**Date:** 2026-10-20. **Provider:** Blaxel. **Result:** Across 8 sandboxes left idle after one
short command, Blaxel billed compute for 22.7 to 34.8 s after the command returned and nothing
for the rest of the idle time, whether the idle lasted 180 s or 360 s. The destroy call added no
billed compute. Each sandbox's metrics cost appeared within a minute of create, while the sandbox
was still alive. The cost reached its final value 45 to 113 s after destroy returned, then stayed
the same for at least 31 minutes. The final value includes snapshot storage for the time in
standby.

## Question

How long after its last command does an idle Blaxel sandbox stop being billed for compute (enter
standby)? How soon after a sandbox ends does its cost appear in Blaxel's metrics API, and when does
that figure stop changing? The revisit window in the billing record (2 hours to 7 days) was set
before any lag had been timed.

## Method

- **Sandboxes:** 8, all 4096 MiB (4 GB), region `us-was-1`, on Blaxel's `blaxel/base-image:latest`.
  Each was created through BoxRouter's adapter for Blaxel with a run label and a
  15-minute lifetime, and destroyed and deleted at the end. At most 4 ran at a time. No create was
  refused.
- **What we did:** each sandbox ran one command, `echo hi`, as soon as the create call returned.
  When that command returned, no further call was made to the sandbox for a fixed idle time:
  180 s for sandboxes 1, 3, 5 and 7, and 360 s for sandboxes 2, 4, 6 and 8. Then the sandbox was
  destroyed. The adapter's destroy call returns once Blaxel reports the sandbox terminated.
- **Our times:** for the create, command and destroy calls, the moment each was sent and the moment
  each returned, from our own clock.
- **The provider's figures:** Blaxel's metrics API, `GET /v0/accounts/{account}/metrics` with
  `resolution=hourly` and `groupBy=resource_uuid`, the request BoxRouter's adapter for Blaxel makes.
  The account held other work, so every page was read by following `meta.nextCursor` with the
  `cursor` parameter. Reads started before the first create and repeated every 60 s. They stopped
  once every sandbox's cost had stayed unchanged for 30 minutes after both its last change and its
  destroy. The window crossed an hour boundary. After the last read, one read with
  `groupBy=resource_uuid,billing_dimension` split each cost by billing dimension.
- **Billed compute seconds:** the `sandbox_compute_runtime_gbs` usage divided by 4 GB. The usage
  equals the compute cost divided by $0.0000115 per GB-second in every row, and is a whole number
  of seconds.
- **Time to standby:** billing runs from create returned (see the billing-boundary check of
  2026-10-11). Billed compute seconds therefore cover two spans. The first is from create returned
  to the command returning (0.23 to 0.32 s here). The second is from the command returning until
  the sandbox entered standby. Time to standby = billed compute seconds - (create returned to
  command returned). Billed seconds are truncated to whole seconds, so the true value lies between
  that figure and 1 s more. No compute was added by the destroy call (see Verdict), so nothing is
  subtracted for it.
- **Lag:** each figure is given as an interval between two reads 60 s apart: the last read without
  the value and the first read with it.

## Results

Times in milliseconds unless marked. "Standby GB" is the snapshot storage usage divided by the
seconds in standby, taken as the life minus the billed compute seconds.

| # | Idle (s) | create call | command call | destroy call | create returned to command returned | Life, create returned to destroy returned (s) | Billed compute (s) | Time to standby (s) | Snapshot storage (GB-s) | Standby GB | Cost first present (s after create returned) | Cost final (s after destroy returned) | Unchanged afterwards (min) |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: | --- | --- | ---: |
| 1 | 180 | 567 | 315 | 3,217 | 315 | 183.5 | 30 | 29.7 to 30.7 | 36.0 | 0.235 | -3 to +57 | +53 to +113 | 39 |
| 2 | 360 | 566 | 303 | 2,497 | 303 | 362.8 | 25 | 24.7 to 25.7 | 79.6 | 0.236 | -5 to +55 | -8 to +52 | 37 |
| 3 | 180 | 477 | 282 | 3,704 | 282 | 184.0 | 23 | 22.7 to 23.7 | 37.8 | 0.235 | -7 to +53 | +49 to +109 | 39 |
| 4 | 360 | 433 | 307 | 2,977 | 307 | 363.3 | 30 | 29.7 to 30.7 | 78.1 | 0.234 | -9 to +51 | -12 to +48 | 37 |
| 5 | 180 | 539 | 318 | 3,547 | 318 | 183.9 | 27 | 26.7 to 27.7 | 36.7 | 0.234 | -7 to +53 | -11 to +49 | 37 |
| 6 | 360 | 408 | 275 | 2,957 | 275 | 363.2 | 32 | 31.7 to 32.7 | 77.8 | 0.235 | -11 to +49 | -15 to +45 | 34 |
| 7 | 180 | 528 | 277 | 3,164 | 277 | 183.4 | 32 | 31.7 to 32.7 | 35.5 | 0.235 | -9 to +51 | -12 to +48 | 34 |
| 8 | 360 | 385 | 227 | 3,078 | 227 | 363.3 | 34 | 33.8 to 34.8 | 77.8 | 0.236 | -11 to +49 | -15 to +45 | 31 |

Costs (USD):

| # | Compute | Snapshot storage | Total (`groupBy=resource_uuid`) |
| ---: | ---: | ---: | ---: |
| 1 | 0.001380 | 0.000002778 | 0.001382778 |
| 2 | 0.001150 | 0.000006145 | 0.001156145 |
| 3 | 0.001058 | 0.000002918 | 0.001060918 |
| 4 | 0.001380 | 0.000006029 | 0.001386029 |
| 5 | 0.001242 | 0.000002833 | 0.001244833 |
| 6 | 0.001472 | 0.000006004 | 0.001478004 |
| 7 | 0.001472 | 0.000002742 | 0.001474742 |
| 8 | 0.001564 | 0.000005999 | 0.001569999 |
| All | 0.010718 | 0.000035449 | 0.010753448 |

How each total changed between reads:

- **First present:** the first value seen was the compute cost alone, and it never changed
  afterwards.
- **Before destroy:** while the sandbox was in standby, the snapshot storage part was added in
  steps.
- **After destroy:** the last step appeared in the first or second read after destroy returned.
- **Afterwards:** no further change, including across the 07:00 UTC hour boundary.
- **Missing rows:** in one read, 49 to 53 s after they were destroyed, the rows for sandboxes 1
  and 3 were missing. That read was one complete page, not a partial page. The rows were back in
  the next read with their final values. This is why the "Cost final" interval for those two
  starts after destroy.

## Verdict

- **Time to standby:**
  - The sandboxes were billed for 22.7 to 34.8 s after their last command returned. The lower
    bounds average 27.7 s for the 180-s idle group and 30.0 s for the 360-s group.
  - Doubling the idle time did not change the billed compute, so idle time after standby is not
    billed as compute.
  - The figure matches the 2026-10-09 probes (23.5 to 33 s) and the earlier standby batch (about
    20 to 27 s billed after the connection was lost).
  - Blaxel's pages say "approximately 15 seconds" (overview) and "about 5 seconds" (pricing page
    FAQ). Every sandbox here took longer than both.
- **Destroy of a sandbox in standby:**
  - The compute figure was in the metrics, at its final value, before the destroy call was sent.
    It did not change afterwards.
  - The destroy call (2.5 to 3.7 s) therefore did not wake the sandbox into billed compute.
- **Snapshot storage:**
  - While a sandbox is in standby, Blaxel bills `sandbox_snapshot_storage_gbs` for it: about
    0.235 GB for the base image, at $7.716e-8 per GB-second. That rate is $0.20 per GB-month for a
    30-day month, the listed snapshot rate.
  - In the `groupBy=resource_uuid` read, this charge is part of the sandbox's own cost. It is why
    these totals are not whole seconds of compute.
  - In the `groupBy=resource_uuid,billing_dimension` read, the snapshot row has the sandbox's
    resource UUID but a different resource name. A match on the sandbox's name in that grouping
    finds the compute row only.
  - Here the snapshot storage was 0.2% to 0.5% of each sandbox's cost.
- **Metrics lag:**
  - Each sandbox's compute cost was present within 49 to 57 s of create returned. That is about
    20 to 30 s after the sandbox entered standby, and before it was destroyed.
  - The total reached its final value 45 to 113 s after destroy returned: for 6 sandboxes within
    45 to 52 s, and for the 2 whose rows went missing within 109 to 113 s.
  - No value changed in the following 31 to 39 minutes.
  - A read made 2 minutes after destroy returned would have found the final figure for all 8
    sandboxes. A read made at destroy returned would have missed only snapshot storage, 0.2% to
    0.5% of the cost.

## Limits

- 8 sandboxes in one account, one region, one size (4096 MiB) and one small image, on one morning
  (06:25 to 07:09 UTC). Blaxel's Billing Explorer page says to expect a lag of a few minutes,
  sometimes longer under load; this batch saw no such load.
- Reads were 60 s apart, so each appearance and settle time is known only to that interval.
- Each figure was followed for 31 to 39 minutes after it settled, not for days. How long a figure
  is kept was not measured.
- Each sandbox was active once, from create to its first standby, about 30 s. A sandbox that
  stays active for long, or one that wakes from standby, may report its compute later or in steps;
  that was not tested here.
- The command used the adapter's normal persistent HTTP client, which can keep an idle connection
  open after the last request; time to standby was measured from the last request, not from the
  close of that connection.
- Time to standby assumes billing starts at create returned. If it started at create sent, each
  figure would be 0.4 to 0.6 s shorter.
- The account held more than 100 metrics rows for the window, so the figures needed every page of
  the response; a single page would not have contained them.
