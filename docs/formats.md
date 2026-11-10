# Formats

Eight JSON Schemas (draft 2020-12) in [`schemas/`](../schemas/) define every document this package
reads or writes. The wheel ships them as `sandbox_provider_pricing/schemas/`. Money and rates are
decimal strings, never JSON numbers.

| Schema | One document is | Written by |
| --- | --- | --- |
| [`price-version`](../schemas/price-version.schema.json) | What one provider charged from one date: rates, meter rules, sources and exclusions. | Contributors, in `src/sandbox_provider_pricing/providers/<name>/prices/` |
| [`billing`](../schemas/billing.schema.json) | One provider's billing rules, best cost label and revisit window. | Contributors, as `src/sandbox_provider_pricing/providers/<name>/billing.yaml` |
| [`record`](../schemas/record.schema.json) | What a consumer stored about one sandbox: provider and id, the size, class and region asked for, its own call edges, the Core reports as read, the provider's records and times. | You, as the input to `record_evidence()` ([using records](using-price.md#building-evidence-from-a-stored-record)) |
| [`evidence`](../schemas/evidence.schema.json) | What you collected about one sandbox: the request, call times and the provider's records. | `record_evidence()`, as the input to `price()` |
| [`usage`](../schemas/usage.schema.json) | What one sandbox used. Every fact says where it came from and when. | The provider's rules, inside `price()` |
| [`cost`](../schemas/cost.schema.json) | One usage record priced at one price version. | `calculator.cost()` |
| [`result`](../schemas/result.schema.json) | The full answer for one sandbox, with every step kept. | `price()` |
| [`cost-method`](../schemas/cost-method.schema.json) | The method behind every cost: the shared rules, and for each provider its billing rules and every price version, with sources. | `cost_method()`, and each release as `cost-method.json` ([cost method](cost-method.md)) |
| [`price-sheet`](../schemas/price-sheet.schema.json) | Current display prices and billing rules for every provider, each figure with its source and the date it was checked. A size with no published price is `in_development`, never free. | `build_price_sheet()`, and each release as `price-sheet.json` ([price sheet](price-sheet.md)) |

[`examples/`](../examples/) holds a valid price version, usage record and cost, and
`cost-unknown.json`, a cost with a `null` total.

## Price versions

A price version is named `<provider>@<date>`, with a UTC time added when several are recorded on
one day, and its file is `src/sandbox_provider_pricing/providers/<provider>/prices/<date>.yaml`. It is in effect from its
`effective_from` until the next version takes over.

A released price version never changes, because a service may store it by content hash and price
past sandboxes with it. A correction, even of a typo, is a new version that names the ones it
replaces in `supersedes`.

`seed_versions()` returns every bundled price version as a parsed document, sorted by provider and
file name. It reads them through `importlib.resources`, so it does not depend on where the package
is installed. A service that stores price versions can load its first ones from it.
