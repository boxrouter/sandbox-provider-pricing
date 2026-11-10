# Billing boundary and standby against per-sandbox metrics

**Date:** 2026-10-11. **Provider:** Blaxel. **Result:** Across 25 sandboxes, Blaxel's per-sandbox
cost fits billing from "create returned" to "destroy returned", in whole seconds truncated;
sandboxes idle with no connection were billed for less than their life. The check did not
cover a cold, large custom image, and it cannot tell "create sent" from "create returned" for
a create call as short as 0.2 to 0.4 s.

## Question

When does Blaxel start and stop billing a sandbox relative to the create and destroy calls,
what rounding does it apply, and is standby time billed? Blaxel's pages say memory is billed
while a sandbox is active and not in standby, but not which API call moments bound the bill,
or how seconds are rounded.

## Method

- **Sandboxes:** 25 in the main batch, all 4096 MiB (4 GB), region `us-was-1`.
  - Rows 1 to 20: BoxRouter's standard image, version 0.2.1, already built in the workspace
    (cached).
  - Rows 21 to 25: Blaxel's `blaxel/base-image:latest`.
  - Cold large image: not run. Blaxel refuses a bare registry reference; a brought image must
    first be built into the workspace.
- **What we did:** each sandbox was created through BoxRouter's adapter for Blaxel, held a
  command open for 120 s (20 s commands back to back, so a connection stayed active), then
  was destroyed and deleted. Each carried a run label. The account allows 10 sandboxes at a
  time and other work used some, so the batch ran 4 at a time. Creates the quota refused were
  retried and are not in the table.
- **Our times:** for the create and destroy calls, the moment each was sent and the moment
  each returned, from our own clock.
- **The provider's figures:** Blaxel's metrics API, `GET /v0/accounts/{account}/metrics` with
  `resolution=hourly` and `groupBy=resource_uuid`, read after the batch ended. The per-sandbox
  cost was present at once; no quiet hour was needed because the cost is per sandbox.
- **Normalization:** billed seconds = cost / ($0.0000115 per GB-second x 4 GB). Every cost came out
  as a whole number of seconds at that rate; 4.096 GB (4096 MiB read as decimal GB) did not fit.
  Times below are in milliseconds. A negative residual means the bill is shorter than the span.

## Results

| # | Image | create call (ms) | destroy call (ms) | create returned to destroy sent (ms) | create sent to destroy returned (ms) | Billed (s) | billed minus (create returned to destroy returned) (ms) | billed minus (create sent to destroy returned) (ms) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | standard 0.2.1 | 269 | 2,269 | 120,139 | 122,677 | 122 | -408 | -677 |
| 2 | standard 0.2.1 | 237 | 2,266 | 120,047 | 122,550 | 122 | -313 | -550 |
| 3 | standard 0.2.1 | 296 | 4,518 | 120,079 | 124,892 | 124 | -597 | -892 |
| 4 | standard 0.2.1 | 2,130 | 2,216 | 120,106 | 124,452 | 122 | -322 | -2,452 |
| 5 | standard 0.2.1 | 254 | 2,784 | 120,120 | 123,158 | 122 | -903 | -1,158 |
| 6 | standard 0.2.1 | 414 | 3,900 | 120,071 | 124,385 | 123 | -971 | -1,385 |
| 7 | standard 0.2.1 | 406 | 3,299 | 120,163 | 123,868 | 122 | -1,461 | -1,868 |
| 8 | standard 0.2.1 | 399 | 2,308 | 120,168 | 122,875 | 122 | -476 | -875 |
| 9 | standard 0.2.1 | 404 | 2,843 | 120,155 | 123,403 | 122 | -998 | -1,403 |
| 10 | standard 0.2.1 | 246 | 2,253 | 120,110 | 122,608 | 122 | -362 | -608 |
| 11 | standard 0.2.1 | 228 | 2,780 | 120,121 | 123,129 | 122 | -901 | -1,129 |
| 12 | standard 0.2.1 | 242 | 2,808 | 120,095 | 123,144 | 123 | 98 | -144 |
| 13 | standard 0.2.1 | 271 | 2,321 | 120,138 | 122,731 | 122 | -459 | -731 |
| 14 | standard 0.2.1 | 269 | 2,799 | 120,150 | 123,219 | 122 | -949 | -1,219 |
| 15 | standard 0.2.1 | 318 | 2,835 | 120,094 | 123,247 | 122 | -929 | -1,247 |
| 16 | standard 0.2.1 | 253 | 2,757 | 120,116 | 123,126 | 123 | 127 | -126 |
| 17 | standard 0.2.1 | 312 | 2,323 | 120,114 | 122,748 | 122 | -437 | -748 |
| 18 | standard 0.2.1 | 239 | 2,351 | 120,089 | 122,679 | 122 | -440 | -679 |
| 19 | standard 0.2.1 | 238 | 2,945 | 120,100 | 123,283 | 123 | -45 | -283 |
| 20 | standard 0.2.1 | 272 | 2,248 | 120,117 | 122,637 | 122 | -365 | -637 |
| 21 | blaxel/base-image | 306 | 2,281 | 120,158 | 122,745 | 122 | -439 | -745 |
| 22 | blaxel/base-image | 290 | 3,469 | 120,129 | 123,888 | 123 | -598 | -888 |
| 23 | blaxel/base-image | 253 | 4,513 | 120,118 | 124,884 | 123 | -1,631 | -1,884 |
| 24 | blaxel/base-image | 287 | 2,372 | 120,074 | 122,733 | 122 | -446 | -733 |
| 25 | blaxel/base-image | 250 | 2,897 | 120,128 | 123,275 | 123 | -25 | -275 |

Totals for the 20 standard-image sandboxes (seconds):

| Span | Seconds |
| --- | ---: |
| Blaxel billed | 2,446 |
| create returned to destroy returned | 2,457 |
| create sent to destroy returned | 2,465 |
| create returned to destroy sent | 2,402 |
| create sent to destroy sent | 2,410 |

The average gap of -0.55 s between billed and "create returned to destroy returned" is what
truncation to whole seconds produces. For the 5 base-image rows: billed 613 s; 616 s from create
returned to destroy returned; 618 s from create sent to destroy returned.

### Standby (earlier batch, same day)

A first attempt held each sandbox's command through a client error. That left 19 sandboxes alive
for about 245 s each, with no connection after the command failed (about 120 s in; the exact
time of the error was not recorded). Their cost was 140 to 147 billed seconds (4 GB). Their
lives, create returned to destroy returned, were 243 to 246 s, so billing was 97 to 106 s less
than the life. The time after the connection ended was not billed in full.

### Time to enter standby

Blaxel's Sandboxes overview says a sandbox without an active connection moves to standby in
"approximately 15 seconds". Separate probes (2026-10-09, with all connections closed) found
standby 25 to 33 s after the last command in 7 of 10 trials that waited 30 s, and 23.5 to
31.3 s after the last request in 9 of 9 trials with the adapter's normal persistent client at
waits of 60, 120 and 300 s. Further runs put the figure at 30 to 60 s. The probe write-up is
not in this repository, and only these summary figures are recorded here. Blaxel's pricing page
FAQ now says "about 5 seconds"; the pages disagree with each other and with the measurement.

## Verdict

- **End:** billing ends at about destroy returned. The destroy call takes 2 to 5 s, and ending
  the bill at destroy sent would make the 20-sandbox batch 44 s (1.8%) shorter than billed. Clear.
- **Start:** weaker. The create call is 0.2 to 0.4 s (0.3% of a 120 s sandbox). The total fits
  create returned better than create sent. Row 4, whose create took 2.13 s, was billed 122 s,
  against 122.3 s from create returned and 124.5 s from create sent. That is one row.
- **Row by row:** with billing from create returned to destroy returned truncated to whole
  seconds, each row's "billed minus (create returned to destroy returned)" should fall between
  -1,000 and 0 ms. 21 of the 25 rows do. Rows 12 (+98 ms) and 16 (+127 ms) were billed slightly
  more than the whole span, and rows 7 (-1,461 ms) and 23 (-1,631 ms) were billed 0.46 and
  0.63 s less than truncation allows. The batch totals still fit; these four rows are not
  explained.
- **Rounding:** whole seconds, truncated. Every cost was a whole number of seconds at
  $0.0000115 per GB-second of 4 GB. The metrics figure therefore equals the list-price
  calculation for active time.
- **Image:** the 5 base-image rows fit the same boundary, so it did not depend on the image among
  these two small ones.
- **Standby:** idle time with no connection was billed for less than the sandbox's life. The
  batch does not say which instants counted as active, so a calculation from our call times
  alone is an upper bound; the metrics figure is the measure.
- **Timing of the figure:** the per-sandbox cost was in the metrics as soon as the batch ended.

## Limits

- 25 sandboxes in one account, one region, one size (4096 MiB), one 2-minute workload.
- Cold large custom image not run; image loading at create is not settled.
- The standby batch has no per-sandbox table here, and the time of the connection error was not
  recorded.
- One time-to-standby probe write-up is not included, so those figures cannot be rechecked from
  this repository.
- "Available at once" was observed for one batch on one day; Blaxel's docs say expect a lag of a
  few minutes, sometimes longer under load.
