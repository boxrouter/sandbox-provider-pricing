# Composing resource costs

Use `compose()` when one trial or sandbox group is made of several resources or several sandboxes,
each priced with `price()`. Pass a result for every sandbox, snapshot, volume and failed creation attempt in the
group.

```python
from sandbox_provider_pricing import compose, price

parts = [price(evidence) for evidence in resource_evidence]
trial_cost = compose(parts)
print(trial_cost["label"], trial_cost["total"])
```

The total is the sum of the parts only when every part has an exact total. One unknown or ranged
part makes the group total unknown. The group's label is its weakest part's: `unknown`, then
`calculated`, then `reported`.

Beside the total, the composed result carries what a reader of one sandbox's result expects:
`lines` (the parts' lines, none while the total is unknown), `held_back_by` and `excluded` (each
reason once), `reported` (the parts' provider-reported costs added, when every part has one),
`final` (true only when every part is), `versions` (the first part's), `as_of` (the latest) and
`steps.usage` (the parts' usage added). `next_read()` takes a composed result too.

`parts` keeps every result in full, with its evidence, usage, rates and failed-attempt facts.
`revisits` lists `{"part": index, "revisit": obligation}`, so each resource keeps its own window
for re-reading late records. Store the composed document as the group's result. Do not rebuild its
total yourself or pick one part's revisit schedule for the whole group.

Every part must be in USD, with a supported label and a `total` field. An unknown total is valid
input. An empty list is refused, since it describes no trial or group.
