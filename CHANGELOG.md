# Changelog

All notable changes to this package are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and [RELEASE.md](RELEASE.md) says how
releases are made.

## 0.17.4 — 2026-11-13

### Added

- Superserve prices its default class: price version `superserve@2026-11-13` has CPU at
  $0.000014 per vCPU-second and memory at $0.0000045 per GiB-second, billed while a sandbox runs,
  the same on every plan. Storage is left unpriced: the pricing page lists it at $0.000108 per
  GiB-hour while retained, and the public pricing data marks it not billable, so the version states
  disk, snapshot and image storage as unbounded. Billing boundaries and per-sandbox records are not
  measured, so the cost label is unknown.

## 0.17.3 — 2026-11-12

### Added

- Agent37 prices VM instances: price version `agent37@2026-11-12` adds class `vm` at 2.5x the
  default compute rate ($2.00 per vCPU-month and $1.75 per GB-month of RAM) with disk unchanged at
  $0.09 per GB-month, and supersedes `agent37@2026-11-11`.
- A price class may carry `derived_from` (`class`, `factor`, `rates`) where the provider publishes
  a rate only as a factor of another class's: each named rate equals that class's rate times the
  factor, in the same unit, and a source quote states the factor (`watch.verify` checks both).

## 0.17.2 — 2026-11-11

### Changed

- Every rate unit (`per`) enum in the price-version schema also states `type: string`: OpenAPI
  accepts `x-boxrouter-open-enum` only on a string enum, so its clients widen the unit to any
  string.

## 0.17.1 — 2026-11-11

### Changed

- Every rate unit (`per`) enum in the price-version schema carries `x-boxrouter-open-enum: true`:
  units grow with the provider roster, so readers take the listed units plus any string. The
  listed units are unchanged; a test checks that every `per` enum carries the flag.

## 0.17.0 — 2026-11-11

### Added

- Agent37 is priced: price version `agent37@2026-11-11` (CPU, RAM and disk per month, metered per
  minute), its billing rules, and a rule that reports a deleted instance's settled
  `compute_micros` from Agent37's usage report as the sandbox's cost, labelled `reported`.
  Managed LLM, search and tool spend billed to the instance is left out.
- Rates can be per month: `vcpu-month`, `gib-month` and `gb-month`, where a month is 730 hours.
  The price-version and price-sheet schemas list the new units.

### Fixed

- The price sheet checks that a running price's CPU and memory parts add up on the calculator's
  exact figures, so an hour of a monthly rate, a decimal that does not end, no longer fails on
  float rounding. A storage row's `price_version_rate.per` must now be its rate's own unit.
- The cost method accepts a price version without `supersedes`, as the schema does.

## 0.16.3 — 2026-11-10

### Changed

- The price-sheet schema types `content_criteria`: the field references `$defs.content_criteria`,
  a constant holding the criteria that `x-content-criteria` held before. A sheet whose criteria
  differ no longer validates, and generated types carry each criterion instead of an open object.

### Fixed

- boxd: the benchmark region's source link names Sandbox Provider Spec v0.3.178 (line 29), a
  version published on the public spec repository; v0.3.161 predates it and is not published.

## 0.16.2 — 2026-11-10

### Fixed

- boxd's complete USD usage record is priced as reported when the consumer keeps no create or
  destroy call edge: the record's own `period.start` selects the stored list rates it is checked
  against, where the sandbox had no start. Before, such a record read unknown ("the provider did
  not report the billed time") though it was complete and its rates matched.

## 0.16.1 — 2026-11-09

### Changed

- The price-sheet schema requires what every sheet already carries: top-level `sizes` and
  `default_size`, `pages.pricing`, each provider's `display_name` and storage `status_text`, and a
  non-null provider `source_url` (a price version always has a source). `panels` also types its
  values for a consumer that indexes it by key, still with exactly the four panel ids. Each bounded
  sentence reaches `$defs/sentence` through `allOf`, so generated types name it once. The sheet
  itself is unchanged; `schema_version` stays `2.4.0`.

### Removed

- `evidence.validate_call_times`, a relaxed check of raw benchmark call records that no consumer calls.

## 0.16.0 — 2026-11-09

### Added

- Price sheet 2.4.0: each provider entry carries `unit_rates`, the hourly price of one vCPU and of
  one GiB of memory while running (`cpu_per_vcpu_hour`, `memory_per_gib_hour`), converted from the
  price version's own rate units with the region multiplier. vCPUs times the one plus GiB times the
  other is every size's running price; a consumer no longer divides a sized figure to show a rate.

### Changed

- Breaking: the sheet's `schema_version` is `2.4.0` and the provider schema requires `unit_rates`.
- The price-version `machine_rates` description no longer lists one provider's size names; it
  describes the keys as the provider's own size names.

## 0.15.0 — 2026-11-08

### Added

- `billable` receives the price-version pool in effect as `versions`, and `stored_rates_match`
  accepts it, so a provider can check a record's rates against the version actually in use rather
  than only the bundled pool.

### Changed

- Billing records state `reported_under_account_rate`: whether a provider's reported cost is what
  the account pays (a partner discount lowers it; the figure is supplier cost only and the
  customer charge is priced from list rates), the public list cost whatever the account pays, or
  unverified (treated as account-rate). Every provider states it; the schema keeps it optional in
  earlier rules versions. `reported_at_list_price` keeps its meaning: whether a reported figure
  earns the `reported` label.

## 0.14.1 — 2026-11-07

### Changed

- Blaxel has a new current price version that supersedes its last with no rate or class change. It
  states the sandbox's own filesystem as not billed separately (`coverage.disk`): the writable layer
  is in the RAM the memory rate bills, and Blaxel's billing API lists only compute runtime, image
  storage and snapshot storage as sandbox dimensions. A Blaxel reservation quote is `bounded` again.

## 0.14.0 — 2026-11-07

### Added

- Price versions carry `coverage`: every billable charge (`cpu`, `memory`, `disk`, `creation`,
  `egress`, `snapshot_storage`, `image_storage`, `volume_storage`, `requests`) stated as `in_quote`,
  `not_billed` or `unbounded`, each with its source. Every provider has a new current version that
  supersedes its last with no rate, class or source change.

### Changed

- Breaking: `reservation_quote` returns `unknown` when a charge is left unstated or contradicts the
  rate card, and for any price version without `coverage`. It returns `unbounded` when coverage
  states cpu, memory or disk as unbounded (Blaxel, Modal), and lists each unbounded non-running
  charge in `excluded`. Consumers move to the new versions in the same repin.

## 0.13.0 — 2026-11-07

### Added

- Price sheet 2.3.0: each provider entry carries `billing_mode` (`allocated`, `active`,
  `larger_of_request_and_use`, or `mixed` when its compute meters differ), `active_time_priced`,
  and `compute_rates`, one entry per compute resource charged while running with the meter's
  `basis` and `billed_states` and the rate's own `per`, `usd` and `size_per_unit`. They are
  projected from the price version's meter and rate rules and the billing file's
  `active_time_priced` fact, so a consumer no longer infers the billing mode from prose or from
  a zero-low range.

### Changed

- Breaking: the sheet's `schema_version` is `2.3.0` and the provider schema requires the three new
  fields. There is no 2.2.0 compatibility layer; consumers move to the new pin.

## 0.12.0 — 2026-11-06

### Added

- `lifecycle_quote(version, size, periods)` prices one supplied lifecycle without provider
  evidence. Missing material demand returns an unknown quote with no amount.

### Fixed

- Clarify Boat's wallet and invoice extra starts, stopped-disk retention, and pre-delete usage basis.
- Clarify which lifecycle quote inputs apply per period and which apply to the whole lifecycle.

## 0.11.0 — 2026-11-05

### Added

- Price versions: `volume_storage` may carry `included_gb` and `included_unit`, the volume storage a
  provider includes before its rate applies; the price sheet's volume row shows it as Daytona's disk
  row does. Modal's volume row records its "1 TiB / mo free" as 1024 GiB (`modal@2026-11-05-065700Z`).

## 0.10.0 — 2026-11-05

### Added

- Price sheet 2.2.0: `unit_names`, the display name of each storage unit (`gib-month` is
  `GiB-month`), and `billing_rule_titles`, each billing rule's key and heading in page order, so a
  consumer types neither.
- Modal `volume_storage`: $0.09 per GiB-month, from the pricing page (`modal@2026-11-05-055300Z`).

### Changed

- Billing answers name price rows (`{rate.cpu}`, `{storage.snapshot}`, `{storage.unit}`) and the
  loader fills them from the price version in effect, so no answer types a rate. Blaxel's storage
  rates now read per GiB-month, the unit its price rows bill; boxd's rates read `$` like the others.

## 0.9.0 — 2026-11-05

### Added

- `cost-method.json`: `method.state_titles` gives a consumer the words for the settlement states
  that have no provenance label — `Pending` while a late record can still arrive, `Unknown` once
  none can — keyed by `cost.state`; `exact` keeps the label's title. Cost-method schema 1.2.0.
- `billing.yaml`: a `class_overrides` entry may carry `label`, the class name the price sheet
  shows, owned in billing instead of an outside registry.

### Fixed

- `parse_time` returns a naive datetime unchanged so the designed rejection guards apply on every
  host; aware input still normalizes to UTC.

## 0.8.1 — 2026-11-03

### Fixed

- boxd: the price sheet now records the benchmark region `boxd:eu-fra` from the released Sandbox Provider Spec v0.3.161 declaration. This is BoxRouter's existing benchmark placement, not a new provider location promise.

## 0.8.0 — 2026-11-02

### Removed

- The price sheet's panel `what_this_measures` text and its `details.what-it-measures` slot; nothing read them.

### Added

- boxd: sourced USD usage rates, billing rules, dated evidence and synthetic fixtures. Complete machine usage is reported only when its identity, currency and rates match; missing usage never becomes an allocation estimate.
- Fixture generation now creates a result for a new fixture instead of requiring an existing result file.
- boxd: a managed reservation's ceiling is the size's allocation times the sourced unit rates, used only to bound the hold, never shown as a cost.

### Fixed

- boxd: the price version comes from the recorded create when the provider reports no lifecycle times, so a complete usage record can settle a managed hold.

## 0.7.0 — 2026-11-01

### Added

- `usage.read_before_end(evidence, record)`: for a provider that deletes its per-sandbox record with the sandbox, tells a rule whether a record was read no later than the sandbox's known end (a returned destroy, or noticed gone). A price result's `reported` may now carry `taken_at`, the time of that last read, and a rule that uses it labels the figure as of the read. Boat counts its last usage read before the delete this way (its meter may still be running then), and its revisit window shrinks to 15 minutes because no later read can improve it.

- `rates.machine`: a flat per-size machine rate type for providers that sell a bundle with no published per-unit split. Each entry is keyed by the provider's size name and carries `usd`, `per` (`machine-second` or `machine-hour`) and the bundle's `cpu` and `memory_gib`; a `machine` meter rule says when it is billed. `cost`, `per_hour`, `reservation_quote`, the price sheet and the rate checks price it.
- Boat: billing rules, a sourced price version, reported-cost rules (`GET /sandboxes/{id}/usage` dollars at list price), a fixture, conformance cases and the generated provider page and sheet facts. Its flat per-size hourly rates are recorded as `machine` rates, so the sheet now shows a list price on its three on-grid sizes; per-sandbox cost comes from Boat's reported figure.
- A flat-rate provider renders in the hourly table and price sheet as "flat per-size" instead of failing when neither CPU nor memory is metered; `price_sheet.benchmark_region` may now record `null` for a provider that publishes no region.

## 0.6.0 — 2026-10-31

### Removed

- The `assumed` source is gone from the usage, cost, evidence and result schemas, the cost-method labels and `CERTAINTY`. Nothing produced it, and a cost is the provider's figure or a calculation from provider-reported facts, never a guess. A record that carries `assumed` no longer validates.

## 0.5.33 — 2026-10-31

### Fixed

- A provider whose `billing.yaml` declares `revisit: null`, as a newly scaffolded provider does, now prices: `price()` returns the unknown result with `revisit: null` and `final: false`, and `next_read()` schedules no read. It raised `provider has no revisit policy`, which stopped a benchmark trial of the new provider. `revisit()` still raises for a provider with no policy; `scheduled_revisit()` returns `None`.

## 0.5.32 — 2026-10-31

### Changed

- E2B: new price version `e2b@2026-10-31-015028Z`, same rates. e2b.dev/pricing now starts Enterprise at a $2,000/mo commit with 500 concurrent sandboxes included (was a $3,000/mo minimum) and rewords the concurrency add-ons; the plan-fee exclusion and the two quotes follow it. `conformance.json` records the new check date, and results priced with the new version list the new exclusion text.

## 0.5.31 — 2026-10-31

### Changed

No price or `conformance.json` change; no existing fixture result changes.

- Blaxel and Daytona report a Core cost report's periods only when they leave out none of the sandbox's life. The first period starts within a minute of the sandbox's start (its provider start, else the create call's return), the last ends within a minute of its end (its provider end, else the destroy call's return), and no gap is longer than a minute; a period without both times cannot show coverage. Otherwise the cost stays `unknown` and the read repeats, as before for a sandbox whose figure had not all arrived. This was Cloud's `covers()` check, which kept its own total but not the figure `price()` showed; it is now a rule here (`usage.covers_sandbox`). When the sandbox's start or end is not known there is nothing to compare the periods with, and the report stays reported. Fixtures `core-cost-report`, `core-cost-report-partial` and `core-cost-report-gap` for each of the two.

## 0.5.30 — 2026-10-30

No price, result or `conformance.json` changes.

### Added

- `region_name(region, provider)` is public: a region without our `<provider>:` prefix, as `record_evidence` names it.

### Changed

- `compose()` of a single result keeps that result's total digit for digit instead of writing it to 28 significant digits.

## 0.5.29 — 2026-10-30

### Added

No price, result or `conformance.json` changes.

- `cost_method(provider, prices, rules)` returns the method that priced a result: the price version's rates and sources, and the label, formula and billing rules of the `rules_version` the result recorded as `versions.rules`, not only the newest. Each provider's package keeps a superseded `rules_version`'s document in `billing-history/<n>.yaml` (Modal 2 and 3 today; version 1 was another format and is not kept), and `cost-method.json` carries them under each provider's `rules_history`. `cost-method.schema.json` is 1.1.0.
- Each label in `cost-method.json` has a `title`, the words a consumer shows beside a cost: `Reported By Provider` or `Calculated`, and none for `unknown`. They are written in `METHOD.md`.

## 0.5.28 — 2026-10-30

### Added

No price, result or `conformance.json` changes.

- `spp check-imports` accepts the names in the `__all__` of three submodules, imported as `from sandbox_provider_pricing.<module> import name`: `watch` (the daily price check and its draft: `check_version`, `fetch_page`, `PageText`, `VersionCheck`, `draft_version`, `Outcome`, `DraftError`, `ask_claude`), `conformance` (`load_cases`, `evidence_for`, `run_cases`, `cost_answer`, `sheet_answer`) and `testing`. Reading `watch` does not import the agent's SDK until `ask_claude` is called.
- `sandbox_provider_pricing.testing` is for a consumer's tests: `bundled_providers()` is the folder of provider packages this release ships, `use_providers(root)` prices from the provider folders under `root` for the length of a block (a provider that is not bundled imports its `rules.py` from there), and `forget_caches()` drops what pricing remembers from earlier reads.

## 0.5.27 — 2026-10-30

### Added

- `record_evidence(record)` turns what a consumer stored about a sandbox into the evidence `price()` takes, with `schemas/record.schema.json`. It is the one builder behind Cloud's `provider_evidence` and the runner's `evidence()`: provider times keep only the provider's own of a kind pricing takes, the region loses our `<provider>:` prefix, our call edges become `calls`, and a report without a read time takes the newest read, then `usage.observed_at`, then the record's `read_at`.
- `merge_reports(reads)` joins several reads of one sandbox's Core reports (the runner's `report_merge`, now shared): a later report replaces an earlier one only if it has readings or records, a cost report that is not `available` never replaces one that is, usage records join by (id, scope, source), and each kind keeps its own read time.
- `next_read(result, ended_at, now)` is the one schedule for reading provider records again. It folds Cloud's "read sooner while the price is unknown" into the revisit policy: `RevisitPolicy` and the `revisit:` block of `billing.yaml` take `unpriced_window_s` (default 1800) and `unpriced_first_s` (default 15), Cloud's constants.
- `compose()` takes the sandboxes of one trial, as the runner summed them: `lines`, `held_back_by`, `excluded`, `reported`, `final`, `versions`, `as_of` and `steps.usage` are added, with the same label ranking (any unknown makes it unknown; reported only when all are).
- The evidence schema takes `operations`, and an `image.prepare` that ran leaves the result `unknown` with the held-back code `preparation_cost_unavailable` (the runner's rule, now in pricing).
- `find_class`, `covered_classes`, `latest_version` and `price_version` are public (`__all__`).
- `spp check-imports <path>` lists every `sandbox_provider_pricing` name under a path that is not in `__all__`, and exits 1 if there is any.

No price, fixture result or `conformance.json` changes.

## 0.5.26 — 2026-10-30

### Added

No price, result or `conformance.json` changes: every fixture result and conformance case is identical to 0.5.25.

- `explain(result)` words a `price()` result's working as plain data: one line per charge (`CPU: 0.003067 vCPU-hour × $0.128 per vCPU-hour = $0.00039`) with the exact numbers beside the text and where each came from (provider record, published rate, calculated), and a one-line summary of the total or of why there is none. A `reported` result has one line, the provider's figure. The words are the `x-text` templates in `schemas/cost-method.schema.json`, checked with the other price text.
- `cost_method(provider=None, version=None)` returns the cost method as plain data, and the release publishes it as `cost-method.json` with `cost-method.schema.json` (also in `SHA256SUMS`). It holds `METHOD.md`'s rules as slots (what a cost is, list price against a bill, what never produces a cost, and the three labels), and for every provider its label, formula, what holds it back and would raise it, billing rules with their sources, open questions and measurements, and every price version with its rates, effective dates, sources, what it leaves out and its open questions. A version is keyed by the id a result records as `versions.prices`, so a consumer renders the method of the version that priced a cost. `spp-cost-method --out FILE` writes it.
- `METHOD.md` marks the paragraphs that become slots with `<!-- cost-method: name -->`, and the wheel now carries `METHOD.md`.

### Changed

- The README provider-status table and the provider pages are written from `cost_method()`, the same code as `cost-method.json`, so they cannot disagree. Each page's first line now takes the label's meaning from the `METHOD.md` glossary.

## 0.5.25 — 2026-10-30

0.5.24 was tagged but never published: its release stopped at the REUSE check (a license header written out inside `scaffold.py`). This release has the same changes with that fixed.

### Changed

No price, result or `conformance.json` changes: every fixture result and conformance case is identical to 0.5.23.

- Each provider is now a package in `src/sandbox_provider_pricing/providers/<id>/` (`billing.yaml`, `prices/`, `read-time.json`, `rules.py`). Rules are ordinary importable modules, `sandbox_provider_pricing.providers.<id>.rules`, type-checked and linted with the package, and found through one root. The wheel holds the same files at the same paths. `spp scaffold` and the guide to adding a provider use the new layout.
- `read-time.json` and `tests/read-time-uses.json` name functions and count their uses (`Name:as_of`) instead of recording column positions, so moving code no longer invalidates them. The read-time contract number stays 1: the declaration's shape is unchanged.
- Provider-specific cases left the generic modules: Vercel's and E2B's conformance cases are in their provider folders (`conformance.py`), and Modal's billing-report rule for the evidence schema is `providers/modal/record-rules.json`, which the evidence validator adds to `schemas/evidence.schema.json`. The billing schema accepts `src/sandbox_provider_pricing/providers/...` source paths.
- One `_util.py` holds the time parser, decimal text and package version; the copies in `price`, `versions`, `compose`, `usage` and `price_sheet` are gone. `seed_versions()` copies with `bundled_copy` like every other reader.
- In `price-sheet.json`, `billing_rules_source` and the repository paths inside billing-rule sources now name the files at their new paths (`src/sandbox_provider_pricing/providers/<id>/...`); no rate or text changed.
- Repository tidying: `REUSE.toml` no longer lists deleted workflows, `RELEASE.md` lists `conformance.json` among the release assets, and `AGENTS.md` names the two pinned artifacts the repository consumes.

## 0.5.23 — 2026-10-30

### Fixed

- Record Modal's rewritten sandbox resources page in `modal@2026-10-30-103442Z` (the docs page now says "You’re charged
  max(request, actual) for both CPU and memory" instead of "billed by the second based on whichever is
  higher"; the billing rule and every rate are unchanged), so the daily price check confirms Modal again
  instead of finding a changed page every day.

## 0.5.22 — 2026-10-29

### Fixed

- Record E2B's reworded plan text in `e2b@2026-10-29-203000Z` (the page now writes "(+usage costs)" and "in
  credits", and a tooltip sits inside the Hobby list; no rate changed), so the daily price check confirms E2B
  again instead of finding a changed page every day.

## 0.5.21 — 2026-10-29

### Fixed

- Record Modal's reworded Sandbox pricing section in `modal@2026-10-29-163500Z` (the page now says "Modal
  Sandbox pricing" and labels CPU and memory "non-preemptible"; no rate changed), so the daily price check
  confirms Modal again instead of finding a changed page every day.

## 0.5.20 — 2026-10-29

### Fixed

- Concurrent first reads of provider billing rules wait for initialization before using the module.

## 0.5.19 — 2026-10-29

### Added

- Add `volume_storage` to the price-version schema and record Blaxel's volume rate, $0.12 / GB-month of
  provisioned capacity, in `blaxel@2026-10-29-023000Z` (read from the raw pricing page; no rate changed).
  The price sheet now lists Blaxel volume storage as priced instead of pending.

## 0.5.18 — 2026-10-29

### Changed

- Publish pricing page, section navigation and machine-size labels for consuming websites.
- Keep closed implementation revisions out of current public documents using the shared provenance checker.

## 0.5.17 — 2026-10-28

### Changed

- Use compact quantity and rate-unit axis labels while preserving the full hourly billing basis in chart descriptions.

## 0.5.16 — 2026-10-28

### Changed

- Publish complete pricing disclosure sentences, preserving punctuation when several storage reasons are joined.

## 0.5.15 — 2026-10-28

### Added

- Price a Modal image preparation from its own App (Modal rules version 4): the report target names no sandbox, only the App and account; the report must show the App stopped, a complete read with no sandbox, function or class in it, and the preparation's key and recorded outcome. A failed preparation is priced the same way. An hour with no row is USD 0 only when the request covered it and it had closed before the read; anything missing stays unknown. Evidence `report_target.sandbox_id` may now be null.

- `compose` counts a provider billing hour that several reported parts share, such as one Modal App hour, once; the same hour reported with different amounts leaves the total unknown.

### Changed

- Use shared tooltip slots and finite-predicate descriptions; emit ranking reason fragments with tooltip punctuation supplied by the shared template.

- Read execution-class labels from the locked class registry; keep an unlabeled class as its recorded identifier.

- Use the class registry's "VM" label for Daytona's VM class.

- Identify the cost, price-version and usage schemas as `urn:boxrouter:sandbox-provider-pricing:…`, like the other schemas; the old `urn:boxrouter:provider-pricing:…` identifiers are gone, with no alias.

- Price about a quarter faster with byte-identical results: bundled billing documents and price
  versions are copied from a serialized form, plain JSON evidence skips the Core report checks, and
  the validation memo keys values by `marshal` instead of sorted JSON.

- Generate complete price captions from the shared metric template and bind list-price limits to the existing exclusions.

- Define price text templates and exported slot criteria in the sheet schema; reject fragments,
  missing Details fields, duplicate paragraphs and literal numeric facts in authored text.

- Publish complete pricing chart captions, quantity and unit axis titles, and a title for every panel.

- Export stable criteria slots for pricing hovers and check authored price-page text with the
  shared benchmark verifier.

- Generate storage status hover sentences from schema-owned templates with the storage kind as
  the declared runtime value.

## 0.5.5

### Added

- Publish price-panel captions and axis measures with parameters for the selected size and
  inactive-time shares.

## 0.5.4

### Added

- Publish the active-use measurement explanation with the price sheet, using its conversion
  and exclusion data, and share the storage explanations between panels.

## 0.5.3

### Fixed

- Preserve unchanged conformance cases while verifying release inputs and publication snapshots.

## 0.5.2

### Added

- Ship reproducible conformance cases and a callable verifier for evidence costs, hourly rates,
  lifecycle states, storage statuses and fractional billing boundaries.

## 0.5.0

### Added

- Add the pricing page text, panel details, size labels, provider and class display names, and
  storage status words to the generated price sheet.
- Add structured hourly conversion and excluded price factors to the price sheet contract.

### Fixed

- When a provider's reported cost is read (Blaxel, Daytona, Modal), a usage interval without billed
  seconds now says "No billed seconds for this sandbox: the provider reports its cost instead."
  It no longer says it is waiting for the provider's record beside a reported total. Before the
  report is read, it still says it is waiting.
- A usage report whose `observed_at` is null (Core's pending-events report) no longer makes the
  evidence invalid when every report has its own read time: 0.4.41 checked that field even when
  nothing used it. It is now checked only when a report falls back to it.
- Evidence with a usage report's `observed_at` and no `read_at` is accepted again, as 0.4.39
  documented: 0.4.40 refused it. A report's read time is now its own `read_times[kind]`, then the
  bundle `read_at`, then `usage.observed_at`. A malformed time is still refused.
- Preserve each Core report's actual input read time with optional `provider_reports.read_times`.
  An early Blaxel cost report no longer becomes accepted merely because the pricing read advances.
  Target-only envelopes need no time; explicit bundle `read_at` remains the fallback.

- Publish read-time contract 1: opt-in provider settlement bounds, substitution paths, reviewed-use manifests and late-read samples. See [the contract](docs/read-time-contract.md).

- Provider billing rules load from packaged provider folders; providers without custom rules use the shared default.

### Changed

- E2B costs require the execution allocation in each ending lifecycle event; Core size reports
  and whole-sandbox sizes no longer fill missing allocations. Missing size leaves the cost unknown.
  Changed fixture: `providers/e2b/fixtures/best/result.json` (previously used the requested size).
  Generic `core.size` evidence decoding stays for reproducing stored report documents.

### Changed

- A cost has two labels, `reported` and `calculated`; `unknown` means there is no cost, and
  consumers show none. Shown sandbox times are the consumer's own; provider times only price.

- A recorded exact billing-report request window lets pricing count a
  covered hour with no returned row as USD 0 when that window covers the full sandbox span. Missing
  rows remain unknown without that window.

- Pricing copies the bundled price version and billing document with a plain tree copy instead of
  `copy.deepcopy`, and checks a proven document's new read times with the schema's timestamp
  pattern directly: pricing a sandbox again takes about a third less CPU. Results are unchanged.

### Fixed

- A sandbox with no recorded class is priced only when its price version has one class; with multiple
  classes, its cost is unknown until the class is reported.

### Changed

- Evidence already found valid is not validated again when only its provider records' `read_at`
  times differ (each new time is still checked), and `revisit()` reads the bundled billing
  document without copying it: pricing the same sandbox at a later read takes about half the CPU.
  Results are unchanged.
- The E2B rule checks only the evidence fields it derived (its provider times, and records from a Core
  report) instead of validating the whole document again: E2B pricing takes about a third less CPU.
- Daytona's first cost read waits 120 s after the sandbox ends (`revisit.after_s`, was 0): its
  analytics row arrived at most 68.2 s after destroy in 10 measured sandboxes.

### Added

- `steps.sandbox_start`: when the sandbox started, from a provider lifecycle time or else the create
  return, never a cost report's `interval_start`.
- `steps.sandbox_end`: when the sandbox ended, from a provider lifecycle time or else the destroy
  return, never a cost report's `interval_end` (`steps.times.end` still carries the report's period
  for choosing a price version).
- Evidence may carry `requested.class`, the spec class the sandbox was created in; `price()` writes
  it into the usage record's `class` (source `recorded`), so the covering price class rates it.
- A price class may list `covers`, the spec classes it prices; a usage record's `class` names a
  spec class, and a class no price class covers stays unknown. Modal's `default` covers `default`
  and `vm`, and Daytona's `on-demand` covers `container` and `vm`, in new price versions
  `modal@2026-10-24-065000Z` and `daytona@2026-10-24-065000Z` that change no rate.

### Changed

- `price()` validates its evidence once; its rules no longer validate the same object again.
  Rules called directly still validate what they are given.
- `price()` copies only the price version it selected, not every bundled version, and reads the
  package version once per process: about 40% less CPU per call.
- The price sheet (schema 2.0.0) has one entry per `(provider, class)`, keyed by `id` and the new `class`,
  the spec class id (`default` and `vm` for Modal, `container` and `vm` for Daytona, `default` for the
  rest), taken from the default price class's `covers`. Rates are unchanged. Daytona's paused note says
  a VM keeps memory and a container is stopped; the new `class_rules` hold what only some classes say
  (Daytona: archive is container only; Modal VM: the fixed 512 GiB disk is not billed separately). The
  sheet carries no class labels: Core's class discovery owns them.
- The price sheet (schema 1.1.0) names Vercel "Vercel" instead of "Vercel Sandbox" and publishes every
  storage price per GiB-month, with the source's own price and unit in `source_usd` and `source_per`.
  No rate changes.
- Modal's rule reads the workspace and environment from the report target's `account` identity
  (`provider_reports.target`, kept as `evidence.report_target`) instead of
  `requested.options.modal_namespace`, which is removed. A missing, malformed, repeated or
  mismatched identity leaves the cost unknown.

### Fixed

- The usage record's `started` is the sandbox's own start (a provider lifecycle time, else the create
  return), never a cost report's `interval_start`: a Modal sandbox created at 17:16:53Z no longer
  reads as started at 17:00:00Z. `steps.times.start` still carries the report's period.

- A sandbox with no provider times yet now says "The provider did not report the billed time."
  instead of "No price version is in effect".

## 0.4.17

### Changed

- Shorter, plainer wording in every provider's billing record (status, revisit rationale, summary,
  formula and several answers), so the provider pages and price sheet read better. No fact changed.

## 0.4.16

### Changed

- `sandbox_provider_pricing.calculator` is a package: `spans`, `findings`, `quantities`, `charges`
  and `documents`. It still exports `cost`, `per_hour` and its other public names.
- `watch/draft.py` keeps drafting itself; the prompt is in `watch/prompt.py`, the checks in
  `watch/verify.py` and `DraftError` in `watch/errors.py`. `watch.draft` still exports them.

## 0.4.15

### Changed

- One `sandbox_provider_pricing.types` module holds the JSON types: `Document` (an object read as
  input), `JsonObject` (an object built here) and the typed `Evidence`, `BillableUsage`, `Cost`,
  `Finding` and `TimeValue`. `cost()` is typed as returning `Cost`.

## 0.4.14

### Changed

- Provider rules are modules in `sandbox_provider_pricing.rules`, listed in one registry, instead of
  `providers/<name>/rules.py` files loaded by path. `providers/<name>/` holds data and docs only.
- A rule module's `billable` takes `(evidence, billing, *, as_of=None)`; the unused `prices`
  argument is gone.
- `sandbox_provider_pricing.timeline` is now `sandbox_provider_pricing.usage`.
- The Vercel reconciliation moved to `providers/vercel/evidence/reconciliations/`, and
  `spp reconcile` expects that layout.

### Fixed

- Broken links in the Modal billing record and a Daytona evidence file; a test now checks every
  repository link and heading anchor.

## 0.4.13

### Changed

- Rewrite the README and move reference material into `docs/`: using `price()`, reservation
  quotes, the calculator, formats, watching prices and adding a provider.
- Generated provider pages cite sources as footnotes and list every price version with what
  replaced it.
- Generate COMPARING.md's hourly table from the newest price versions; a test fails when it is
  stale.
- Move GOVERNANCE.md, MAINTAINERS.md and CODE_OF_CONDUCT.md into `.github/`.

### Added

- `template/provider/prices/YYYY-MM-DD.yaml`, a starting price version with the editor schema
  header.

### Removed

- `template/README.md`, replaced by `docs/adding-a-provider.md`.

## 0.4.12

### Added

- `make update-fixtures` regenerates fixture results; `make release-digests` records released
  price files.
- Editor schema headers in every `billing.yaml` and in drafts written by `spp draft --out`.

### Changed

- The package docstring lists every public function, and `__all__` is sorted.

## 0.4.11

### Changed

- Keep a Core cost report's `records` (`source`, `read_at`, `body`) unchanged as provider
  records for each provider's rule. Blaxel reads its metrics record when the report has no
  readings.

## 0.4.10

### Added

- Report Modal's hourly per-App bill as the sandbox's cost when the App held only that sandbox
  and its delayed rows are complete.

### Changed

- The price sheet covers a neutral grid of sizes, and callers can choose their own.

## 0.4.9

### Added

- `compose()` adds exact resource costs into one trial or group total, keeping each part's
  evidence and revisit window.

## 0.4.8

### Fixed

- The Modal per-App evidence no longer points at a local path.

## 0.4.7

### Added

- `revisit(provider)` returns the provider's retry policy, and results include `final` and
  `revisit.next_read_at`.
- Every provider has a retry window, marked where it is an unverified default.

## 0.4.6

### Added

- Modal per-App bill evidence from 325 sandboxes.

## 0.4.5

### Added

- The price sheet and its JSON Schema, built from current price versions and billing rules and
  published with each release.

## 0.4.4

### Fixed

- A Blaxel cost report read before the revisit delay is no longer trusted.

## 0.4.3

### Fixed

- Usage records accept exact snapshot sizes with no maximum, and Vercel session start times are
  normalized to UTC.
- Priced usage and cost documents are validated against their schemas for every fixture.

## 0.4.2

### Changed

- Assumed usage, and calculated usage without retained sources, is `unknown`.
- Plainer reasons when a provider report is missing.

## 0.4.1

### Changed

- Keep Core cost report period times for rate selection and revisit windows.
- `reproduce()` works for reported amounts with no price version.

## 0.4.0

### Added

- `price(evidence)` accepts Core reports in `evidence.provider_reports` and interprets E2B events
  and Vercel sessions and snapshots in provider rules.
- `reservation_quote()` and `ReservationQuote` give a spending ceiling for a size and duration, or
  `unbounded` for rates billed on the larger of request and use.

### Changed

- Breaking: a sandbox cost is only `reported`, `calculated` or `unknown`. An unknown total is
  `null` with no lines. The `estimated` label and unbounded totals are gone, and
  `examples/cost-at-least.json` is now `cost-unknown.json`.
- Rule versions advance to 2. `default_billable(evidence, *, as_of=None)` reads provider lifecycle
  times only.
- Modal costs are unknown. Blaxel and Daytona need the provider's reported cost, and Vercel needs
  session usage and snapshot sizes.
- E2B running segments come from lifecycle event timestamps, not `execution_time`.
- Assumed or bounded inputs no longer produce a total. `per_hour` and `hourly` still return ranges.

### Removed

- `BillingBoundary`, `billing_boundary`, `price_intervals`, the `boundary` billing field and
  fallback intervals from our own call times.

## 0.3.30

### Changed

- Start and end times taken from our own create or destroy call are described in plain words.

## 0.3.28

### Added

- `image_storage` in the price-version schema, and Blaxel's deployment-image rate in
  `blaxel@2026-10-23-032207Z`.

## 0.3.25

### Removed

- Price versions dated before 2026-10-20.

## 0.3.23

### Changed

- A shorter provider template: summary, one-line formula, generated rates, nine billing rules,
  open questions and measurements.

## 0.3.19

### Added

- 2026-10-20 price versions for all five providers, with the same rates and self-contained notes.

## 0.3.18

### Added

- The provider template, with a check that fails when a section is missing.
- GOVERNANCE.md, MAINTAINERS.md, CODE_OF_CONDUCT.md and issue templates for price corrections and
  new providers.

Earlier releases, including the rename from `provider-pricing`, are recorded only in the Git
history.
