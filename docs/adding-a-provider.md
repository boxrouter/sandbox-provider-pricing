# Adding a provider

Every provider is described the same way, so a reader can see in a minute how one sandbox's cost
is worked out and check each step. You write two kinds of file by hand, a billing record and a
price version. Everything else is generated. The same steps apply when you review or correct an
existing provider.

## Before you start

You need:

- the provider's public pricing page and billing documentation, so you can quote every rate;
- [uv](https://docs.astral.sh/uv/) and a checkout set up as [CONTRIBUTING.md](../CONTRIBUTING.md)
  describes;
- for any rule the documentation does not settle, a measurement you can repeat, or the honest
  answer that it is unknown.

[METHOD.md](../METHOD.md) is the method behind the files, and [COMPARING.md](../COMPARING.md) lists
the unit and basis differences to look for.

## Steps

1. Generate the native billing record, with the provider's registry id:

   ```sh
   spp scaffold acme --name Acme --website https://acme.example
   ```

   This creates the provider's package, `src/sandbox_provider_pricing/providers/acme/`, with its
   `__init__.py` and `billing.yaml`. Existing identities are reused; this command never replaces a
   billing record. Every generated answer is honestly unknown, with no invented polling schedule or
   rate.
2. Prepare a price-version YAML using the [schema](../schemas/price-version.schema.json). Save
   each provider source page locally and write a JSON map from its URL to its saved filename.
   Add a new version with the same scaffold:

   ```sh
   spp scaffold acme --price sourced-price.yaml --sources saved-pages.json
   ```

   This checks the schema, quotes, amounts and units through the same validator used by the
   price watcher. Missing pages or unsupported rates fail before writing anything. `--dry-run`
   lists the proposed files. A new price item or execution class belongs in this sourced version;
   no shared calculator or renderer registration is needed.
3. Replace unknown billing answers only with source evidence. The revisit policy stays null
   until a schedule is supported; use `unverified_default: true` for an explicitly chosen
   polling policy. The native billing schema and checks apply to generated and existing records.
4. If the records need provider logic, add `rules.py` to the provider's package, starting from
   `rules/default.py`; it is an ordinary module, `sandbox_provider_pricing.providers.acme.rules`,
   checked with the rest of the package. A provider with no `rules.py` uses the shared default
   rules. Other provider-specific code goes in the same folder, and generic modules load it by
   name: `conformance.py` adds synthetic cases to `conformance.json` (see
   `providers/vercel/conformance.py`), and `record-rules.json` adds rules to the evidence schema
   for the provider's own records (see `providers/modal/record-rules.json`). To add sourced region,
   billing-state or storage facts to the shared price display, add a `price_sheet` block to
   `billing.yaml` as described in [Price sheet](price-sheet.md). Without that optional block, the
   provider still appears with unknown display facts.
5. Add a fixture: `providers/acme/fixtures/<case>/evidence.json`, at the repository root beside the
   provider's page and evidence, is a recorded input to `price()`.
   Then generate its expected result:

   ```sh
   make update-fixtures
   ```

   This writes `result.json` beside each `evidence.json`. Never edit `result.json` by hand.
6. Generate the provider page and the tables that list every provider, then run the checks:

   ```sh
   make docs
   make check
   ```

To change a published price, add a new price version instead of editing the old file. Its
`supersedes` lists the version it replaces, and only versions still in the checkout. Explain what it
corrects in an `open_questions` entry that starts with `Correction:`.

## Where the files live

A provider has two folders. `src/sandbox_provider_pricing/providers/<id>/` is a Python package that
ships in the wheel: `billing.yaml`, `prices/`, `read-time.json`, and optionally `rules.py`,
`conformance.py` and `record-rules.json`. `providers/<id>/` at the repository root holds what is
written about the provider: `evidence/`, `fixtures/` and the generated `README.md`.

## A short example

A made-up provider, Acme, bills CPU and memory per second as requested while running. Its price
version, below the template's schema header line:

```yaml
provider: acme
version: acme@2026-01-31
effective_from: '2026-01-31T00:00:00Z'
retrieved_at: '2026-01-31T00:00:00Z'
sources:
- url: https://acme.example/pricing
  quote: 'CPU $0.000014/s per vCPU. Memory $0.0000045/s per GiB.'
classes:
- name: default
  default: true
  rates:
    cpu: {usd: '0.000014', per: vcpu-second}
    memory: {usd: '0.0000045', per: gib-second}
  meter:
    cpu: {basis: allocated, billed_states: [running]}
    memory: {basis: allocated, billed_states: [running]}
exclusions:
- 'Plan fee: Pro $20/month.'
open_questions:
- 'Whether paused sandboxes are billed.'
```

Two of its billing rules, one sourced and one unknown:

```yaml
rules:
  rounding:
    answer: Per second, no minimum.
    sources: [https://acme.example/pricing]
  image_pull:
    answer: Not stated; not yet measured.
    unknown_how: Compare billed seconds for a cold large image with a cached one.
```

`make docs` turns these into `providers/acme/README.md` and adds Acme to the README and
COMPARING.md tables.

## When a check fails

| What you see | What to do |
| --- | --- |
| `assert 'TODO' not in ...` in `test_billing.py` | A `TODO` is left in `billing.yaml`. Replace it. |
| `Invalid isoformat string: 'TODO ...'` | A `TODO` is left in a price version's dates. |
| `test_every_price_file_validates_against_the_schema` lists messages | The price version does not match its schema. Each message names the field. |
| `... cpu rate 0.000014 has no source quote` | A rate is not written in any of the version's quotes. Quote the page where it states the rate. |
| `providers/acme/README.md` not found, or a table in README.md or COMPARING.md does not match | Run `make docs` and commit the result. |
| ``Start these files with `# yaml-language-server: ...` `` | The new price file lost its first line. Put the header back. |
| `... supersedes ..., which does not exist` or `does not supersede ..., the version before it` | A new version must list the version it replaces, and only versions still in the checkout. |
| `... was released and has changed` | A released price file was edited. Restore it and add a new version instead. |
| `.../result.json is stale.` with a diff | Run `make update-fixtures` and check the diff is what you meant. |

`make check` also fails when an answer is too long or a source is neither a web page nor a file in
this repository.

## Rules for answers

Each billing rule is one of three kinds:

- Sourced: an `answer` and its `sources`, the provider's pages or files in this repository.
- Not stated: `answer: Not stated ...`, with the pages you read as `sources`.
- Unknown: an `answer` and `unknown_how`, the check that would settle it.

"The provider does not say" and "we have not measured it" are different, and you write them
differently. A missing rate, size or time leaves the cost unknown; it is never zero.

Never type a rate the price version owns; name its row and the loader fills it from the price
version in effect. `{rate.<resource>}` gives a default-class rate with its unit ("$0.047 per
vCPU-hour" for `{rate.cpu}`; `{rate.machine.small}` for a nested one), `{storage.<kind>}` a storage
row ("$0.08 per GB-month"), either with `.amount` for the amount alone, and `{storage.unit}` the
unit the storage rows named in the answer share. Amounts and units are the provider's own, never
converted. A test fails on an answer that types an amount one of the provider's rows holds, or a
per-month storage unit. Length limits count the filled text.

Write the unit and the basis every time: vCPU or physical core, GB or GiB, requested or used. Keep
each answer to one or two sentences and put tables and method in an evidence file. Name a product
only to identify it, never to praise or criticize it.

## Evidence files

A measurement goes in `providers/<name>/evidence/<date>-<slug>.md`, written from
[the evidence template](../template/provider/evidence/check.md), with a line in `checks` in
`billing.yaml`. It states the question, the method (how many sandboxes, the size, region and image,
cold or cached), every measurement, the verdict and its limits, so anyone can repeat it on their
own account. It names no accounts, credentials or people.

## Please do not

- edit a generated file: provider pages, the tables between `generated` markers, or fixture
  results;
- edit a released price version, even to fix a typo;
- guess a figure the provider does not publish, or write `0` for something unknown;
- use our own call times or clocks as the provider's billing times;
- cite a price aggregator or a third-party page as a source.
