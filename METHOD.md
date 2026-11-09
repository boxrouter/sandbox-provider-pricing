# How sandbox costs are worked out

## What a cost is

<!-- cost-method: what_a_cost_is -->
A sandbox's cost is what the provider charges for that one sandbox at its published list price.

<!-- cost-method: list_price_vs_bill -->
It leaves out account credits, free allowances, discounts, commitments, plan fees and taxes, and each
result lists what it left out under `excluded`. It is not an invoice and not what a customer is
charged.

## Choosing the evidence

Use the best evidence the provider gives, in this order.

<!-- cost-method: reported -->
If the provider reports what the sandbox cost, and that figure matches its list prices, the cost is
`reported` with the provider's amount. Keep the provider's record and the check against list price.

<!-- cost-method: calculated -->
If the provider reports the sandbox's usage or lifecycle instead, the cost is `calculated`: that
usage priced at the stored list rates. Keep the provider's timestamps, allocations and meters.

<!-- cost-method: unknown -->
If neither is available, there is no cost. The result is `unknown`: the total is `null` and
`held_back_by` says what is missing. It is never zero, a range or a floor, and a consumer shows no
cost for it rather than a third label.
<!-- /cost-method -->

A consumer words a cost's label as follows, and shows nothing beside an `unknown` cost.

<!-- cost-method: titles -->
- `reported`: Reported By Provider
- `calculated`: Calculated
<!-- /cost-method -->

Each provider's page says which of these it supports and why.

A cost also carries a settlement state, separate from its label: `exact` when it holds a figure,
`pending` while a late record can still arrive inside the revisit window, and `unknown` once none
can. The total stays `null` for `pending` and `unknown`. A consumer words an `exact` cost with its
label's title and the other two states as follows.

<!-- cost-method: state_titles -->
- `pending`: Pending
- `unknown`: Unknown
<!-- /cost-method -->

## What never produces a cost

<!-- cost-method: never_a_cost -->
Our own clocks never price a sandbox. The times we sent create and destroy calls, when we last saw
a sandbox alive or noticed it gone, deadlines and measured billing boundaries can stay in the
evidence for diagnosis, or help schedule the next read of the provider's records. They never stand
in for the provider's times.

The reverse also holds. The provider's times price the sandbox, but the start and end a consumer
shows people are its own measured times. A provider's time appears only in the cost's working.

An input with no source, a quantity known only within bounds, and a missing rate also leave the cost
unknown. An hourly quote for a size, such as `per_hour`, is a rate card and may be a range. It is
never a sandbox's cost.

The sandbox's class selects its rate set. If no class was recorded and the price version has exactly
one class, that class applies. If it has multiple classes, the cost is unknown until the class is
reported.

## Billable states and time

Split the provider's lifecycle records at each start, pause, resume, stop and end. Apply each rate
only to the states it bills, with its minimum and rounding applied per period. Keep the source
facts, the price version and every arithmetic line, so anyone can reproduce the result. Provider
pages give each provider's states and records.

## Late records

Providers publish some records late. Each provider's `billing.yaml` sets a revisit window, measured
from the sandbox's end: when to read first, how often to read again, and when to stop. Its
`rationale` gives the evidence for those numbers, and `unverified_default: true` marks a window we
chose without it.

Inside the window an `unknown` result means the record has not arrived yet, and you read again.
Read again even after a `reported` result, since an early amount can rise. A record that expires
before you collect it leaves the cost unknown. When a better record arrives, keep the earlier
result as history. [Using `price()`](docs/using-price.md#reading-late-records-again) shows the
interface.

## Modal hourly reports

The record body's optional `interval.start` and `interval.end` fields record the exact
`Workspace.billing.report` request bounds. When that recorded window covers every hour from the
sandbox's start through its end, a missing hourly row
means Modal returned no billed amount for that covered hour; it contributes USD 0. The report must
still prove that one App held only the sandbox, include at least one row, contain no duplicate or
out-of-span rows, and be read after the revisit delay. Without a recorded covering window, a missing
hour leaves the cost unknown.

## Checking against a bill

To check stored rates against a provider's bill, convert each billed quantity to the unit of its
rate, multiply by the stored USD rate and compare with the bill. A row matches when the difference
is at most `0.00000000001` USD. Keep the export and the conversion steps with the result, as in
`providers/vercel/evidence/reconciliations/`. `spp reconcile` does the multiplication
([watching prices](docs/watching-prices.md#compare-a-bill-with-the-rates)).

A mismatch is evidence to investigate. It is never a reason to change a rate or hide the row.

## Glossary

| Term | Meaning |
| --- | --- |
| List price | The rate the provider publishes, before credits, discounts or plan fees. |
| Price version | One provider's rates from one date, with a verbatim quote for each. It never changes once released. |
| Meter | One billed quantity, such as CPU time, memory time or egress, with its rate and rules. |
| `reported` | The provider's own cost for the sandbox, matching list price. |
| `calculated` | The provider's own usage records priced at list rates. |
| `unknown` | No provider evidence gives a figure, so there is no cost. The total is `null`. |
| Revisit window | How long to keep reading a provider's late records after a sandbox ends. |
| `held_back_by` | The reasons a cost is not better, one per missing record or rate. |
