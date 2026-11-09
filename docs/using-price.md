# Using `price()`

`price(evidence)` is the one entry point for a sandbox's cost. You collect the provider's records
and keep them; `price()` interprets them. Each provider's interpretation lives in
`src/sandbox_provider_pricing/rules/<provider>.py`, and the calculator only rates the usage those rules derive. Do not
convert meters or call the calculator yourself.

## Evidence from provider usage reports

Pass provider usage reports for the same sandbox and its incarnation. This package accepts
report records and does not import provider SDKs.

```python
from sandbox_provider_pricing import price

# The provider and sandbox identifiers match the reports' sandbox incarnation.
result = price(
    {
        "provider": provider_name,
        "sandbox_id": sandbox_id,
        "provider_reports": {
            "read_times": {"cost": cost_read_at, "size": size_read_at, "usage": usage_read_at},
            "cost": cost_report,
            "size": size_report,
            "usage": usage_report,
        },
    }
)
```

`cost`, `size` and `usage` are each optional. `read_times` maps each present kind to
when that report was actually read: an input observation time, never the current pricing clock.
Each timestamp string is kept verbatim. A report's read time is the first of these that is
present:

1. `read_times[kind]`, that report's own time.
2. The bundle `read_at` (an aware datetime or timestamp string).
3. The usage report's `observed_at`, the form 0.4.39 documented.

A kind with none of them is refused. Malformed times, unknown `read_times` keys and times for
absent kinds are refused. The usage report's `observed_at` may be
null; it is checked only when some report falls back to it. With no reports, no read time is required: a target-only
envelope preserves `target` as `report_target`, including alongside raw provider records.
Pass the current pricing read separately as `price(..., as_of=...)`.

Keep the report records unchanged:

- A usage report's `records` stay grouped by record identity, with `times`, `related_id` and `final`.
  Standalone `.readings` from older reports are kept separate and are never rebuilt into sessions.
- A cost report's `records` (`source`, `read_at` and `body`) pass through unchanged for the provider's rule to read. A record without
  those fields, or whose body is not an object, is refused.

- `target` (`sandbox_id`, `created_at`, `identities` of
  `scope` and `id`) is kept as `evidence["report_target"]`. Pass the latest retained target. Rules
  read identities from it; the caller never names a provider. Modal's rule requires exactly one
  `account` identity whose `id` is the namespace, written as
  `json.dumps({"environment": env, "workspace": ws}, sort_keys=True, separators=(",", ":"),
  ensure_ascii=False)`: exactly those two non-empty string keys. It also requires
  `target.sandbox_id` to equal the evidence `sandbox_id`. A missing, malformed, repeated or
  mismatched identity leaves the cost `unknown`.

Missing or partial records leave the cost `unknown`.

## Provider records you must keep

Some records disappear, so persist them as soon as you read them.

- E2B: keep every lifecycle event and its execution allocation. The API keeps events for 7 days by
  default. Running segments are measured between event timestamps, not from `execution_time`.
- Vercel: keep every session and snapshot, with each snapshot's `related_id` pointing at its
  source session. Keep them before deletion or name reuse makes them impossible to attribute.
  Snapshot sizes stay exact integers, including values too large for a JavaScript number.

A running session or a missing required record gives `unknown`.

Evidence that already holds raw `provider_records`, such as E2B API or webhook events and Vercel
session and snapshot records, is accepted as it is.

## What comes back

The result's main fields are listed in the [README](../README.md#reading-a-result).
`steps.evidence` is the evidence after normalization, and `steps.usage` is the usage the rules
derived from it. `reproduce(result)` re-rates `steps.usage` with the price version named in
`versions.prices`.

## Building evidence from a stored record

Do not build evidence by hand from what you stored. Map your storage to a **record**
([`record.schema.json`](../schemas/record.schema.json)) and let `record_evidence()` do the rest,
so Cloud, the benchmarks and your own service read the same sandbox the same way:

```python
from sandbox_provider_pricing import merge_reports, price, record_evidence

reports = merge_reports(reads)  # every read of the sandbox's Core reports, each with its read_at
evidence = record_evidence(
    {
        "provider": "e2b",
        "sandbox_id": native_id,
        "requested": {"cpu": 2, "memory_mib": 4096, "region": "e2b:us"},
        "reports": reports,
        "provider_records": provider_records,
        "provider_times": provider_times,
        "calls": call_edges,  # our own edges: they stand in for a missing provider time, never price
    }
)
result = price(evidence, as_of=read_at, ended_at=ended_at)
```

- **Reports.** A report keeps the time it was read at (`read_times`). A report with none takes
  the newest read among the envelope's and its records, then the usage report's `observed_at`,
  then the record's `read_at`. A time must carry its zone.
- **Merging reads.** `merge_reports(reads)` takes reads oldest first. A later report replaces an
  earlier one only if it has readings or records, and a cost report that is not `available` never
  replaces one that is. Usage records join by (id, scope, source), so records that a provider's
  API has since dropped stay.
- **Times.** Only the provider's own lifecycle times, of a kind pricing takes, are kept. Our call
  edges become `calls`: the first create and the last destroy, each with its latest send.
- **Region.** Pass it as you recorded it; a leading `<provider>:` is removed.
- **Operations.** An `image.prepare` that ran leaves the sandbox's cost `unknown`
  (`preparation_cost_unavailable`): Core's receipt for it has no billing target.

## Reading late records again

Providers publish some records late. Each provider's `billing.yaml` sets a revisit window: how long
after a sandbox ends to make the first read, how often to read again and when to stop. Inside the
window an `unknown` result means the record has not arrived yet; there is no separate pending
label. Keep reading inside the window even when the result is already `reported`, because early
Daytona amounts have come in low.

Pass the sandbox's end time, if you store it, as `price(evidence, ended_at=...)`. It sets `final`
and `revisit.next_read_at` and changes nothing else. With no known end there is no scheduled
read. Evidence that the sandbox was never created is final at once.

To schedule reads, ask for the next one. `next_read(result, ended_at, now)` returns the time of the
next read, or `None` when none is due. It is the provider's cadence, except that while a price is
still `unknown` shortly after the end it comes sooner: after half the time since the end, at least
`unpriced_first_s` (default 15) from `now`, for the first `unpriced_window_s` (default 1800) after
the end. A provider's `revisit` block in `billing.yaml` may set those two numbers.

```python
from sandbox_provider_pricing import next_read

due = next_read(result, ended_at, now)  # a datetime, or None
```

To read the policy itself:

```python
from sandbox_provider_pricing import revisit

policy = revisit("e2b")  # RevisitPolicy(after_s=15, until_s=604800, interval_s=3600)
policy.next_read(ended_at, last_read_at=last_read_at)  # None after the last read
policy.may_change(ended_at, as_of=now)  # False once the window has closed
```

All times are aware datetimes, and the window is measured from the sandbox's end. A window that
`billing.yaml` marks `unverified_default: true` is our polling choice, not a measured guarantee
that the provider's records are final.
