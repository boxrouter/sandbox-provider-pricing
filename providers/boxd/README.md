# boxd

boxd costs are `reported`. The provider's own cost for the sandbox, matching list price.

CPU time used, resident RAM and written disk are metered every second. Cost comes from machines.usage(id).cost_micro, never from the provisioned machine size.

## How the cost is worked out

A complete USD machines.usage(id) record for this machine, with rates matching the stored list version, reports cost_micro divided by one million. Otherwise unknown; no calculated fallback.

What holds it back: Nothing. Only a complete USD machine usage record with matching machine identity and stored list rates counts.

What would improve it: Nothing. Missing, incomplete, non-USD or mismatched records leave cost unknown.

## Rates

From [`boxd@2026-11-02-082924Z`](../../src/sandbox_provider_pricing/providers/boxd/prices/2026-11-02-082924Z.yaml), in effect from 2026-11-02, default class `default`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| CPU | $0.047 per vCPU-hour | only while in use, in 1 s increments | running |
| Memory | $0.014 per GiB-hour | only while in use, in 1 s increments | running, paused |
| Disk | $0.000096 per GiB-hour | only while in use, in 1 s increments | running, paused, stopped |

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | $0.047 per vCPU-hour of CPU time used, $0.014 per GiB-hour of resident RAM while running or in standby, and $0.000096 per GiB-hour of written disk in every state; never provisioned size. [^1] |
| Billing starts | Not stated where metering begins within create or resume calls; only the provider's usage record supplies cost. [^2] |
| Billing ends | Hibernated and stopped machines still bill written disk; stopping alone does not end all charges. Exact deletion billing edges are not stated by the provider. [^1] |
| Rounding | Metered every second, settled every 15 minutes, with no minimum per machine. Each organization settlement rounds each resource up to the next millionth of its currency; this is not per-machine rounding. [^1] |
| Idle and paused | Idle CPU bills only time used; standby or suspend-to-RAM bills resident RAM and written disk. Hibernation and stopped machines bill written disk only; generic paused represents standby, not hibernation. [^1][^2] |
| Image pull | Not stated whether image pull and restore work is included in the machine meter. To find out: Compare provider usage records for cold and cached images, without substituting call duration. |
| Billed separately | State transitions cost nothing; separate snapshot and custom-domain fees are not stated by the provider on the checked pricing pages. Do not treat unpublished fees as zero. [^1][^2] |
| Left out | No monthly plan, paid-plan minimum or per-seat fee is published for pay as you go. Credits, taxes, custom pricing and annual self-host licences are outside the per-machine USD list cost. [^1][^2] |
| Per-sandbox data | machines.usage(id) returns machine_id, currency, cost_micro, complete, usage quantities and rates; the SDK calls cost_micro an estimate at current rates, not the invoiced settlement. Accept only complete USD records whose identity and rates match. [^3][^4] |

## Not known yet

- Can complete records be corrected later, and how long are deleted-machine records retained?
  - To find out: Re-read a deleted machine's complete usage over days and compare with organization billing activity.
- Are snapshots and custom domains charged separately?
  - To find out: Obtain a published rate or a provider charge record before adding a price; do not infer that they are free.
- Does current-rate cost_micro remain at historical rates when the public rate card changes?
  - To find out: Compare retained records and their rates across a published rate change; rate mismatches remain unknown.

## Our measurements

None yet.

## Price versions

- [`boxd@2026-11-02-082924Z`](../../src/sandbox_provider_pricing/providers/boxd/prices/2026-11-02-082924Z.yaml): from 2026-11-02, read 2026-11-02, in effect now.
- [`boxd@2026-11-02`](../../src/sandbox_provider_pricing/providers/boxd/prices/2026-11-02.yaml): from 2026-11-02, read 2026-11-02, replaced by `boxd@2026-11-02-082924Z`.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/boxd/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [boxd.sh/llms-full.txt](https://boxd.sh/llms-full.txt)
[^2]: [boxd.sh/pricing](https://boxd.sh/pricing)
[^3]: [pypi.org/project/boxd/0.2.22](https://pypi.org/project/boxd/0.2.22/)
[^4]: [2026-11-02-sdk.txt](evidence/2026-11-02-sdk.txt)
