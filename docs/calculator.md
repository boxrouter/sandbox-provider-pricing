# The calculator

`sandbox_provider_pricing.calculator` prices a usage record with a price version. It is pure
arithmetic, with no I/O, no clock and no provider names. Every provider quirk is a meter rule in
the price version, so a new rate is a new file in `src/sandbox_provider_pricing/providers/<name>/prices/` and never a code
change.

Use [`price()`](using-price.md) for a sandbox. It calls the calculator after the provider's rules
have turned its records into usage.

## `cost(usage, version, *, as_of=None)`

Returns a cost document ([schema](../schemas/cost.schema.json)). `version` is the price version
in effect when the sandbox started, or `None` when there was none, which gives `unknown`. `as_of`
defaults to the latest time any usage fact was observed. Pass a later time to read a running
sandbox's cost so far.

The result is `calculated` only when every quantity is exact and came from a retained provider
record. The cost is `unknown`, with a `null` total, no lines and a `held_back_by` reason, when an
input has no source, is only bounded, or has no rate. A request cannot establish use
above itself, so a meter billed on the larger of request and use never produces a total from the
request alone.

## Classes

A usage record's `class` is the sandbox's spec class (`default`, `container`, `vm`). The price
class that prices it is the one whose `covers` lists that class, or whose name it is when the class
has no `covers`. A record that names no class is priced by the default class. A named class that no
price class covers is unknown, with a finding; it is never priced at the default class.
`price()` takes the class from the evidence's `requested.class` (the class the sandbox was created
in, recorded by the caller) and writes it into the usage record with source `recorded`.

## `per_hour(version, size, *, class_name=None, region=None)`

Returns `{"low": ..., "high": ...}` for one hour of running at a size, or `None` when the version
prices nothing the size lists. This is a rate-card quote, not a sandbox cost, and it can be a range:
a meter billed only while in use runs from no use to full use. Creation fees and egress are not
hourly, and minimums do not apply to an hour that carries on.

`size` takes the usage record's size fields: `cpu`, `memory_mib`, `disk_mib`, `gpu` and
`gpu_model`. A resource the size leaves out is not priced. GPU rates are stored per model, named by
the `gpu-registry` identifier. A price version can list discrete `memory_steps_mib`; memory rounds
up to the next listed step, and a size above the largest step is not priced. A `region` applies
that region's multiplier to each line's rate.

A provider that sells a flat bundle with no published per-unit split carries `rates.machine`: one
entry per published size name, each with its `usd`, `per` (`machine-second` or `machine-hour`) and
the bundle's `cpu` and `memory_gib`. A size matching an entry's `cpu` and `memory_mib` is billed
the flat rate; a size that matches no entry is not priced.

`hourly(provider, size, *, at=None)` returns the same range for the bundled version in effect at
`at` (newest by default), with a short basis, the first source URL and the date it was checked:

```python
>>> from sandbox_provider_pricing import hourly
>>> quote = hourly("e2b", {"cpu": 2, "memory_mib": 4096})
>>> quote["low"], quote["high"], quote["basis_text"], quote["checked_at"]
('0.1656', '0.1656', 'allocated CPU and memory', '2026-10-20')
```
