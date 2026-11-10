# Read-time contract 1

`READ_TIME_CONTRACT = 1`, `settles_after(provider) -> int | None`, and `READ_TIME_PATHS`
are public exports. The bound is an integer number of seconds, not a billing period or a
promise that a provider has published its final bill. `None` means no guarantee, including
unknown providers, invalid slugs, absent or malformed declarations, and `settles: never`.

For fixed valid evidence, fixed price versions and the same package, once `as_of` is at least
`settles_after(provider)` seconds past the latest timestamp **anywhere** in the evidence,
`price()` returns the same document at every later valid read, except for verbatim copies of
`as_of` at `READ_TIME_PATHS`. This includes nested record bodies and all diagnostic call times,
not just lifecycle times. Include an explicitly supplied `ended_at` in the latest-input maximum:
it overrides the scheduling anchor. Hold all other arguments fixed. Reads and arithmetic must
remain representable by Python datetime (years 1–9999).

Interpret a date-only string at its latest possible instant in any timezone, rather than at
UTC midnight; a timezone-naive timestamp likewise needs its latest possible UTC interpretation.
Python UTC offsets have magnitude strictly less than 24 hours. A conservative upper limit for
an entire date is its midnight in UTC plus two days. Include datetime fractional precision;
do not truncate the latest-input maximum to whole seconds.

## Paths and substitution

Paths are dot-separated object keys. `*` matches one object key or one list index, never an
arbitrary depth. Missing paths are ignored. Replace a leaf **only when its value equals the
old `as_of` verbatim**; some observation fields instead contain fixed provider record times.
Never replace timestamps throughout the evidence or all strings globally.

- `as_of`
- `steps.rated.*.as_of`
- `steps.usage.*.*.observed_at`
- `steps.usage.*.intervals.*.observed_at`
- `steps.usage.*.intervals.*.size.observed_at`

Record `read_at` values in `steps.evidence` remain input evidence; they are not new read clocks.
For provider-report input times and their precedence, follow the
[provider usage report contract](using-price.md#evidence-from-provider-usage-reports).

## Derivation and provider opt-in

Each provider opts in with `src/sandbox_provider_pricing/providers/<slug>/read-time.json`:
`contract: 1`, `settles: bounded`, and its reviewed `uses` manifest. Custom rules receive no guarantee by
default, even when their billing file has a revisit policy. `settles: never` declines the
contract. An unknown contract number declines it too. A new provider must review its code,
include its own manifest and fixtures, and pass `make check` before claiming the guarantee.

The bound is computed from that provider's `billing.yaml`, not a provider-name whitelist:

```
revisit.after_s + revisit.until_s + revisit.interval_s
+ 86400 + 172800 + 1 + 1 seconds
```

The first three terms cover the first-read offset plus the entire retry window and one full
cadence, even though current scheduling clamps to `end + until_s`. The next terms cover a full
date (86400 seconds), the supremum of the legal timezone-offset spread (172800 seconds),
subsecond precision rounded up (1 second), and a separate strict-comparison margin (1 second).
Modal's one-hour row expansion is smaller than the full-date allowance and is input-derived;
it does not extend with `as_of`. Blaxel and Modal record acceptance compares fixed record
reads to end plus `after_s`; Modal additionally rejects a record read later than `as_of`.
Missing-record explanations compare with end plus `until_s`; finality and revisit use the
same window. There are no other read-dependent offsets in the reviewed implementation.

| Provider | after_s | until_s | interval_s | Bound (seconds) |
| --- | ---: | ---: | ---: | ---: |
| Blaxel | 600 | 604800 | 3600 | 868202 |
| Daytona | 120 | 259200 | 3600 | 522122 |
| E2B | 15 | 604800 | 3600 | 867617 |
| Modal | 600 | 604800 | 3600 | 868202 |
| Vercel | 120 | 604800 | 3600 | 867722 |

These are implementation bounds for fixed inputs. New evidence, prices, rules, or package
versions invalidate that premise. Outputs before settlement, including waiting versus unknown,
finality, and revisit scheduling, keep their existing behavior.

## Enforcement and limitations

This is a **reviewed contract, not a proof**. `tests/read-time-uses.json` owns shared-code
entries; each provider owns entries for its `rules.py` in its declaration. Each entry names the
file, function, classification, offset, and all directly scanned uses. The bounded AST scan
counts names, attributes, parameters, keywords and literal keys for `as_of`, `observed_at` and
names containing `read_at`. It rejects added, moved or removed uses until the manifest is
reviewed. Each use is written `<node type>:<name>`, once per occurrence within its function, so
entries are tied to function names and counts, never to lines or columns.
The clock scan rejects direct/import-aliased `datetime.now`, `utcnow`, `date.today`,
`datetime.today`, `time.time`, and `time.time_ns` calls outside `watch/`.

The samples cover every provider fixture and generated missing-record, missing-terminal,
subsecond/extreme-offset and date-only variants. They compare exactly at the bound, +1 second,
+1 day, +30 days and year 9000 using only the documented substitution. They also exercise just
before the bound without requiring equality, and explicit revisit/finality boundaries.

The scan is not an interpreter or taint analysis. It cannot follow arbitrary aliases, dynamic
lookups, reflection, other clock APIs or changed arithmetic on an existing alias. A manifest
classification is a human assertion; matching uses cannot establish its truth. Samples cannot
exhaust arbitrary record bodies, all datetimes or all custom provider code. Review changes to
helper arithmetic and billing metadata as well as named clock uses. Consumers may additionally
confirm a candidate cached result against a far-future read. No known OpenRouter equivalent
for sandbox evidence settlement is documented in our reference research; this narrow contract
belongs with the calculator that owns the behavior.

Changing the meaning of the guarantee or path syntax requires a new `READ_TIME_CONTRACT`.
A new path or bound can ship in a package release under the same meaning; consumers must read
both from their installed package, and decline unknown contract versions.
