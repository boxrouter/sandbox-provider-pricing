# Price sheet

The package can produce the shared JSON document for BoxRouter price displays. It reads the
latest bundled price version and `src/sandbox_provider_pricing/providers/<provider>/billing.yaml` for every discovered provider
folder. Provider-specific display facts live in that billing file's optional `price_sheet` block;
the block keeps those facts and source URLs beside the provider's billing rules and uses the same
schema validation. Each hourly figure carries its price source URL and checked date; unknown or
unpublished rates stay explicit.

A provider with a billing folder and a price version appears even when it has no `price_sheet`
block. Its region is `null`, idle and paused rates are `null` with notes that those facts are
unrecorded, class rules are empty, and storage is empty unless the price version itself supplies a
storage rate. The running prices still come from its price version.

```sh
make price-sheet
```

This writes `dist/price-sheet.json` and its contract, `dist/price-sheet.schema.json`. The same
builder is available to Python callers:

```python
from sandbox_provider_pricing import build_price_sheet

document = build_price_sheet()
```

The sheet needs nothing but this package. Each provider's `billing.yaml` lists under `shapes` what
each of its spec classes sells: an exact shape (`cpu` and `memory_mib`, each one number) or a range
(`cpu` and `memory_mib` as `[low, high]`, any size inside it; a `null` high means the provider
publishes no maximum). Every entry carries the provider page that states it (`source`), the date it
was read (`checked`), the `quote` that states it as saved under `providers/<id>/evidence/`, and a
`note` for a condition such as a plan requirement. The price version owns what a shape costs: a
provider that publishes one price per named size (Boat) keeps those prices as its flat `machine`
rates, and a test holds the two lists equal. A provider class with no recorded shapes fails the
build and the error names it. The Sandbox Provider Specification declares what BoxRouter can
create; Cloud's `scripts/check_priced_shapes.py` fails when a declared shape has no price here, and
pricing may record more shapes than the specification declares. `exact_sizes=True` prices every
requested size exactly, for callers that price one exact size (the conformance cases do).

Each size in `configs` is priced as the cheapest shape its class offers that is at least that big
(vCPUs and memory both at least the size's; ties go to fewer vCPUs, then less memory). The config
names that shape in `shape`, which equals `size` when the class offers that size. A class that
accepts any size in a range prices the size itself where it is inside the range. A size no offered
shape fits has `status` `not_offered`, a `reason`, a null `shape` and no price; a shape with no
published price is `in_development`.

By default the published sheet covers the Cartesian product of 1, 2, 4 and 8 vCPU with 2, 4, 8
and 16 GiB of memory. This resource grid is the sheet's consumer-neutral coverage; it is not a
benchmark requirement. A consumer can choose its own non-empty, unique set of positive integer
`(vCPU, memory GiB)` pairs:

```python
document = build_price_sheet(price_configs=[(1, 2), (2, 4), (4, 8), (8, 16)])
```

Modal prices use the provider folder's pinned `us` region with the price version's region multiplier.
Blaxel and Vercel display active-time rates at the upper end of the running range. Idle, paused and
storage figures follow the provider folder's sourced display facts and the price version's
structured storage rates.

Each provider's `name` is the display name in the provider's billing file; `display_name` repeats it
for consumers that use the display contract. The `label` identifies the spec class, such as `gVisor`
or `VM`. Storage `usd` is always per GiB-month (`per: gib-month`); a source quoted per GB-month is
converted (× 1.073741824), and `source_usd` and `source_per` keep the provider's own price and unit.
`unit_names` gives the display name of every storage unit in the sheet (`gib-month` is
`GiB-month`), and `billing_rule_titles` each billing rule's key and heading, in page order. Billing
answers state prices from the price version's rows (see
[Rules for answers](adding-a-provider.md#rules-for-answers)).

Each provider entry states its billing mode as typed fields, projected from the price version's
meter and rate rules and the billing file's `active_time_priced` fact; `basis` stays as the
reader's sentence. `billing_mode` is `allocated` (the size the sandbox has), `active` (only while
the resource is in use), `larger_of_request_and_use`, or `mixed` when the running-billed compute
resources differ. `compute_rates` lists each of those resources (`cpu`, `memory` or a flat
per-size `machine`) with its meter `basis` and `billed_states` and the rate's own `per`, `usd` and
`size_per_unit`, before any region multiplier; a flat machine rate has `usd` null and the sized
figures carry its amounts. `active_time_priced` is true where the running figures are collapsed to
the upper end of the range; with `billing_mode` `active` and `active_time_priced` false, the running
range runs from no use to full use.

`unit_rates` gives the hourly price of one vCPU (`cpu_per_vcpu_hour`) and of one GiB of memory
(`memory_per_gib_hour`) while the sandbox runs: each rate converted from its own unit to an hour,
at the upper end and with the benchmark region's multiplier, so vCPUs times the one plus GiB times
the other is a size's running price. `cpu_per_vcpu_hour` is null where the CPU is billed with the
memory, and `unit_rates` is null for a flat per-size machine rate.

The sheet has one entry per provider and spec class (`id` and `class`), the classes being those the
provider's default price class `covers`. The rates are the same for every class of a provider;
`paused_note` and `class_rules` say what differs. `pages.pricing`, `panels`, `hourly`, `excludes`,
`default_size` and `sizes` carry the pricing page text and size labels. Panel fields without a
source fact are omitted. Each storage entry keeps its status word and adds a complete sentence
from the schema-owned status template, resolved with that entry's storage kind. The sentence
describes the status without adding provider-specific rates or billing rules.
