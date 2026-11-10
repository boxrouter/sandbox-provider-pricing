Exported 2026-10-12 07:12 UTC:

```sh
curl -H "Authorization: Bearer $VERCEL_TOKEN" "https://api.vercel.com/v1/billing/charges?slug=<team>&from=2026-10-06T00:00:00.000Z&to=2026-10-13T00:00:00.000Z"
```

Kept: ServiceCategory Sandbox, ConsumedQuantity > 0, periods starting before 2026-10-12.
Removed: Tags (project id and name). Bill days run 07:00 UTC to 07:00 UTC.

The normalized `bill.jsonl` preserves each `ChargePeriodStart` as `period_start`, maps
`ServiceName` to `meter`, uses `EffectiveCost` as `cost_usd`, and converts `ConsumedQuantity`
at export time to the selected price rate's `per` unit:

- Sandbox Active CPU stays in vCPU-hours.
- Sandbox Creations is divided by 1,000,000 to million-creations.
- Sandbox Data Transfer stays in GB.
- Sandbox Provisioned Memory stays in GB-hours.
- Snapshot Storage is multiplied by 24/730 to GB-months because each row covers 24 hours and the
  price version uses `month_hours: '730'`.

Every normalized bill quantity is already in the unit named by its selected rate's `per` field.
`spp reconcile` multiplies `quantity × rate.usd`; it does no unit conversion.

Re-run against the current price version, CPU, creations, memory and snapshot storage still
match. Six data-transfer rows with a nonzero quantity cost $0 on this bill, while the current
version prices data transfer at its $0.15 per GB list rate, so those six rows are unmatched.
The bill is the record of what was charged; the gap is between the list rate and this account's
bill, which the evidence in `../../evidence/2026-10-12-charges-rates-check.md` describes.
