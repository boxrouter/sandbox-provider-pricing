# The cost method and a cost's working

A consumer writes no cost words of its own. This package publishes the words as data: the
method, for every provider and price version, and the working of each result.

## The method: `cost_method()` and `cost-method.json`

```python
from sandbox_provider_pricing import cost_method

cost_method()  # the whole document
cost_method("e2b")  # one provider
cost_method("e2b", result["versions"]["prices"])  # the price version that priced a cost
cost_method("modal", result["versions"]["prices"], result["versions"]["rules"])  # and its rules
```

Each release publishes the whole document as `cost-method.json` with
[`cost-method.schema.json`](../schemas/cost-method.schema.json). It holds:

- `method`: [METHOD.md](../METHOD.md)'s rules as slots, each a list of paragraphs: what a cost is,
  list price against a bill, what never produces a cost, and the three labels, each with its
  `title` (the words a consumer shows beside a cost: `Reported By Provider` or `Calculated`; none
  for `unknown`) and its meaning. `state_titles` holds the words for the settlement states that
  have no label of their own (`Pending`, `Unknown`; `exact` keeps the label's title). METHOD.md
  marks each slot with `<!-- cost-method: name -->`.
- `providers.<id>`: the label it can reach (`best_label`), `summary`, `formula`, `why_not_higher`,
  `would_raise`, the billing `rules` with their sources (`left_out` among them), `open_questions`
  and `measurements`, all from `billing.yaml`, for its newest `rules_version`. `rules_history` holds
  the same fields for each earlier `rules_version`, keyed by the number a result records.
- `providers.<id>.versions.<price version>`: every price version, by effective date with the newest first, with its classes
  and rates, effective dates, `sources` (a URL and verbatim quote each), what it leaves out and
  its open questions, all from `prices/`. A result records the key as `versions.prices`.

A result records both versions it was priced with: `versions.prices` and `versions.rules`.
`cost_method(provider, prices, rules)` returns the method that priced it: that price version's rates,
and that rules version's label, formula and billing rules. Text may contain code spans written with
backticks and nothing else.

## Keeping the rules of old versions

When a change to `billing.yaml` moves its `rules_version`, copy the document it replaces to
`src/sandbox_provider_pricing/providers/<id>/billing-history/<old version>.yaml` in the same pull
request. Never edit a file there; it is what priced results. The tests fail unless every version from
2 up to the current one has its document. Version 1 was a different format and is not kept, so
`cost_method` refuses it.

`spp-cost-method --out cost-method.json` writes the document. The provider pages and the README
table come from the same code (`make docs`), so they cannot disagree with it. Change a sentence in
METHOD.md, `billing.yaml` or a price version, never in code.

## The working: `explain()`

```python
from sandbox_provider_pricing import explain

explained = explain(result)
explained["summary"]  # "Calculated: $0.0032, the sum of the lines above."
for line in explained["lines"]:
    line["text"]  # "CPU: 0.003067 vCPU-hour × $0.128 per vCPU-hour = $0.00039"
    line[
        "sources"
    ]  # {"quantity": "provider record", "rate": "published rate", "amount": "calculated"}
```

A `calculated` result has one line for each charge. A `reported` result has one line, the
provider's figure, sourced to the provider's record. An `unknown` result has no lines, and its
summary gives the first reason in `held_back_by`. Beside each line's text are the exact `quantity`,
`unit`, `rate` and `amount` from the result (and `exact_quantity` when the text rounds the
quantity), and `quantity_source` as the result gives it. The exact amounts add up to the total.
The words are the templates in `schemas/cost-method.schema.json` under `x-text.explain`.
