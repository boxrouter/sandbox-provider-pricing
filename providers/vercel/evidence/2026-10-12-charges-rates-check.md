# Billing charges export against the price version's rates

**Date:** 2026-10-12. **Provider:** Vercel. **Result:** 25 of 26 daily charge rows from the
billing charges API equal quantity × rate from the Vercel price version then in effect; the one row
that differs is a $0.000312 data-transfer charge that the price version prices at $0. This
checks rates and units only, not which moment billing starts or stops.

## Question

Do the rates and units in the price version reproduce what Vercel actually charged? The
pricing page gives the rates; the billing charges API
([List FOCUS billing charges](https://vercel.com/docs/rest-api/billing/list-focus-billing-charges))
returns the charges. Comparing them tests the rates, the units (GB-hours, GB-months, millions
of creations) and the meter set. It does not test a per-sandbox interval, because the charges
are per project per day.

## Method

- **Export:** on 2026-10-12 at about 07:12 UTC, `GET /v1/billing/charges` for one team for
  2026-10-06T00:00:00Z up to 2026-10-13T00:00:00Z. The API returns one FOCUS-style row per
  charge, with one-day granularity, and tags each row with a project. Vercel's bill days run
  from 07:00 UTC to 07:00 UTC.
- **Kept:** rows with `ServiceCategory` Sandbox, `ConsumedQuantity` above zero, and a period
  starting before 2026-10-12. Project tags were removed. 26 rows remained.
- **Compared:** each row's `EffectiveCost` against `ConsumedQuantity` × the rate in price
  version then in effect, after converting the quantity to the unit the rate is written in
  (vCPU-hours stay as they are; creations ÷ 1,000,000; GB stays GB; GB-hours stay GB-hours;
  snapshot storage × 24 ÷ 730 to GB-months, because each row covers 24 hours and the price
  version uses 730 hours per month). A row matches when the two costs differ by no more than
  $0.00000000001.
- **Not included:** the account's plan, credits or allowances, and any row that was not a
  Sandbox service.

The full method, the normalized bill and the per-row result are in
[the reconciliation folder](reconciliations/2026-10-06/how.md)
([bill.jsonl](reconciliations/2026-10-06/bill.jsonl),
[result.json](reconciliations/2026-10-06/result.json)).

## Results

| Meter | Rows | Matched | Rate used |
| --- | ---: | ---: | --- |
| Active CPU | 6 | 6 | $0.128 per vCPU-hour |
| Provisioned memory | 6 | 6 | $0.0212 per GB-hour |
| Creations | 6 | 6 | $0.60 per million |
| Snapshot storage | 1 | 1 | $0.08 per GB-month |
| Data transfer | 7 | 6 | $0 per GB |
| **Total** | **26** | **25** | |

The row that differs: for the bill day starting 2026-10-06 07:00 UTC, one data-transfer row
has quantity 0.002079933 GB and cost $0.00031198995, which is $0.15 per GB. The price version
prices data transfer at $0 per GB, because the pricing page lists it as included in the Flat
Rate CDN on Pro and $0.15 per GB on Enterprise. The other six data-transfer rows (0.011 to
0.50 GB per day) have cost $0. Why one small quantity was priced at $0.15 per GB is not
explained by the export. Price version `vercel@2026-10-20-055630Z` later priced data transfer
at $0.15 per GB, the iad1 rate in the pricing page's regional table.

Memory and CPU quantities were 3.8 to 69.6 GB-hours and 0.15 to 8.5 vCPU-hours per day over
the window.

## Verdict

Supported: the memory, active CPU, creation and snapshot-storage rates and units in the price
version reproduce Vercel's charges to within $0.00000000001 on every one of their 19 rows,
including the 24-hour-to-month conversion for snapshot storage.

Not settled: the data-transfer rate. One row was charged $0.15 per GB while six were charged
$0, so the price version's $0 holds for most but not all of the data in this export.

Not tested: when memory billing starts and stops for one sandbox, whether any rounding to
1-minute increments shows in the daily totals, and what Vercel did with credits or allowances
(the comparison uses `EffectiveCost`).

## Limits

- One team, one week, one export. Quantities are per project per day, so no single sandbox can
  be compared.
- The matched rows prove the rates agree with the export, not that the export is complete.
- Rates are for the default region (`iad1`); the pricing page says CPU, memory and data
  transfer rates vary by region, and the region of each row was not examined.
