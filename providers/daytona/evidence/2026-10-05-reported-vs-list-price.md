# Daytona's per-sandbox price against the list-price calculation

**Date:** 2026-10-05. **Provider:** Daytona. **Result:** On three sandboxes of about 5 seconds,
our list-price calculation over our own call times came out 1.06% to 1.80% below the price
Daytona reported; Daytona's price equals its own billed period multiplied by the list rates,
and the gap matches the 23 to 69 ms by which Daytona's period edges lie outside ours. The
check covers one size and three short runs, and it cannot say why a first read of the same
figures differed (see [Limits](#limits)).

## Question

Is the per-sandbox price Daytona reports the same as the price we calculate at list price? An
earlier comparison had shown our calculation at up to 3.75 times Daytona's figure, which could
have meant a wrong rate, an extra charge on Daytona's side, or a wrong billed interval on ours.
Daytona's documentation does not say how its per-sandbox price is formed.

## Method

- **Sandboxes:** three, created and destroyed one after another, each running about 5 seconds,
  through BoxRouter's adapter for Daytona on a Daytona organization used for testing. Size
  1 vCPU / 1 GiB memory / 3 GiB disk. Inventory returned to its starting count afterwards.
- **Our times:** for each sandbox, the moment the create call returned (the start of our
  interval) and the moment the destroy call was sent (its end), from our own clock.
- **Our calculation:** the interval in seconds multiplied by the list rates of the price version
  dated 2026-10-03 13:09:08Z (since retired; no public release carries it): $0.000014 per
  vCPU-second, $0.0000045 per GiB-second of memory and $0.00000003 per GiB-second of disk. For
  1 / 1 / 3 that is $0.00001859 per second. The 3 GiB of disk is charged in full; the "first 5
  GiB free" allowance on Daytona's pricing page is not subtracted.
- **The provider's figures:** the per-sandbox usage-periods endpoint of Daytona's analytics API
  (`GET /organization/{organizationId}/sandbox/{sandboxId}/usage`), read after the runs. It
  returns each sandbox's billed periods with `startAt`, `endAt` and `price`. The price below is the sum of the
  period prices (one period per sandbox here).

## Results

### Earlier comparison (2026-10-04 runs)

Three completed sandboxes of the same size, using the interval BoxRouter then recorded, which
ended at the timestamp of the destroy response rather than the moment the destroy call was sent.

| # | Daytona period (UTC; length) | Our earlier interval | Daytona price (USD) | Our calculation (USD) | Ours / Daytona |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | 15:01:10.816 to 15:01:11.664 (0.848 s) | about 3.18 s | 0.00001576432 | about 0.0000591 | about 3.75 |
| 2 | 14:27:11.399 to 14:27:12.000 (0.601 s) | 1.547353 s | 0.00001117259 | 0.00002876529227 | 2.575 |
| 3 | 08:01:20.719 to 08:01:21.693 (0.974 s) | 1.817685 s | 0.00001810666 | 0.00003379076415 | 1.866 |

Applying the list rates above to each Daytona period reproduces Daytona's price, so neither a
rate nor an extra disk charge explains the gap. The recorded end times of the earlier intervals
were 0.881 to 2.371 seconds after Daytona's periods ended, so the destroy response had
widened our interval. The interval was changed to end when the destroy call is sent.

### With the destroy-sent end (2026-10-05 runs)

| # | Our interval (UTC; length) | Daytona period (UTC; length) | Daytona price (USD) | Our calculation (USD) | Ours vs Daytona |
| ---: | --- | --- | ---: | ---: | ---: |
| 1 | 18:47:04.943213 to 18:47:10.190752 (5.247539 s) | 18:47:04.911 to 18:47:10.216 (5.305 s) | 0.00009861994999999998 | 0.000097551750 | −1.08% |
| 2 | 18:47:13.990370 to 18:47:19.201315 (5.210945 s) | 18:47:13.957 to 18:47:19.224 (5.267 s) | 0.00009791353 | 0.000096871468 | −1.06% |
| 3 | 18:47:22.905076 to 18:47:28.118716 (5.213640 s) | 18:47:22.836 to 18:47:28.145 (5.309 s) | 0.00009869431000000001 | 0.000096921568 | −1.80% |

Where Daytona's period edges lie relative to ours (milliseconds):

| # | Daytona start before our start (create returned) | Daytona end after our end (destroy sent) |
| ---: | ---: | ---: |
| 1 | 32.213 | 25.248 |
| 2 | 33.370 | 22.685 |
| 3 | 69.076 | 26.284 |

Re-derived from the table above for this file: each Daytona price equals its period length
multiplied by $0.00001859 per second to the last digit shown (5.305 s gives 0.00009861995;
5.267 s gives 0.00009791353; 5.309 s gives 0.00009869431). The rows with the destroy-sent end
agree with Daytona within 5% in every sample.

### Two reads of the same sandboxes

BoxRouter also stored the figure from the first read of Daytona's endpoint for each sandbox. A
later direct read returned the prices in the table above. The first reads were lower:

| # | First read (USD) | Later read (USD) | First vs later |
| ---: | ---: | ---: | ---: |
| 1 | 0.00009460451 | 0.00009861994999999998 | −4.07% |
| 2 | 0.00009374937 | 0.00009791353 | −4.25% |
| 3 | 0.00009599876 | 0.00009869431000000001 | −2.73% |

We did not establish why the two reads differ. The table above uses the later reads, and the
two read paths are recorded separately rather than treated as identical.

## Verdict

- Daytona's reported price for these three sandboxes is its billed period multiplied by the
  list rates, with all 3 GiB of disk charged. A recalculation from the periods matches to the
  last digit shown, so the list rates in the price version reproduce Daytona's own amounts.
- Our calculation over our own call edges is 1.06% to 1.80% below Daytona's price. The gap
  is explained by the edges: Daytona's billed period begins 32 to 69 ms before our start and ends
  23 to 26 ms after our end, which on a 5-second sandbox is about 1 to 2 percent. On a
  10-minute sandbox the same offsets are under 0.02% (see
  [the billing boundary check](2026-10-11-billing-boundary.md)).
- Daytona's amount is list price for its own billed period; our interval is only shorter than
  Daytona's. With the three 2026-10-04 sandboxes above and the seven of
  [the billing boundary check](2026-10-11-billing-boundary.md), Daytona's price equalled its billed periods at list rates in
  all 13 sandboxes measured, so `reported_at_list_price` is true and a complete reported figure
  is labelled `reported` (decided 2026-10-20). Before that the record kept the label at
  `calculated` because our own calculation was not equal to the reported amount.
- It does not show that the first-read figures were wrong, only that they differed.

## Limits

- Three sandboxes, one size (1 vCPU / 1 GiB / 3 GiB), one region and one organization, all
  running about 5 seconds, so every offset is large relative to the run.
- Only running time was compared. Stopped periods are covered in the
  [billing boundary check](2026-10-11-billing-boundary.md).
- Disk was charged in full for 3 GiB; whether the "first 5 GiB free" allowance applies per
  sandbox, per organization or only on the invoice is not settled here.
- Why the first reads of the endpoint differed from the later reads is unexplained.
- Daytona's price was read from the analytics endpoint, not from an invoice, so the invoice
  was not compared.
