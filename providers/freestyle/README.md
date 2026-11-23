# Freestyle

Freestyle costs are `calculated`. The provider's own usage records priced at list rates.

Freestyle meters vCPU and memory per second on the amount allocated while a VM runs, and storage on the amount allocated for as long as the VM exists. It reports no cost for a VM. Its VM record reports the seconds the VM has run (credited when a run ends) and the allocated size, and the record goes with the VM. The cost is therefore calculated from those quantities, read after a pause and before the delete, at the published rates. Without the record it is unknown.

## How the cost is worked out

vCPU-seconds (totalRunSeconds × allocated vCPUs) × the vCPU rate + GiB-seconds of memory (totalRunSeconds × allocated GiB) × the memory rate + GiB-seconds of storage (createdAt to the read × allocated GiB) × the storage rate, each rate per hour divided by 3,600.

What holds it back: Freestyle has no per-VM cost or usage endpoint, so nothing it reports is a dollar figure. The quantities come from its own VM record (totalRunSeconds, createdAt and the allocated size) and are priced at its published list rates.

What would improve it: A per-VM cost or usage API from Freestyle, which its CEO said is planned. Until then the cost is calculated, and without the VM record it is unknown.

## Rates

From [`freestyle@2026-11-23`](../../src/sandbox_provider_pricing/providers/freestyle/prices/2026-11-23.yaml), in effect from 2026-11-23, default class `default`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| CPU | $0.04032 per vCPU-hour | size requested | running |
| Memory | $0.0129 per GiB-hour | size requested | running |
| Disk | $0.000086 per GiB-hour | size requested | running, paused, stopped |
| Network egress | $0.02 per GB |  |  |

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | $0.04032 per vCPU-hour and $0.0129 per GiB-hour of allocated vCPUs and memory while the VM runs, plus $0.000086 per GiB-hour of allocated storage for as long as the VM exists, running or paused. Data transfer across the datacenter boundary is billed per GB. [^1] |
| Billing starts | Not stated. Freestyle's VM record has no started-at field; the seconds of each run are credited to totalRunSeconds when the run ends. Storage is stated to bill for the time the VM is allocated, and the record's createdAt is the only start it gives. [^1][^2] |
| Billing ends | Compute ends when a VM pauses or stops: the pause credits the run to totalRunSeconds at once. Freestyle states no deleted-at time, and the VM record is gone after the delete. [^1][^2] |
| Rounding | Metered per second and billed per hour of resource used; no minimum is stated. totalRunSeconds is whole seconds, and its rounding against our wall times varied by under 1 s per run in both directions. [^1][^3] |
| Idle and paused | A running VM bills its allocated vCPUs and memory whether or not the guest is busy. A paused VM holds no compute reservation and bills only storage. [^1] |
| Image pull | Not stated; not yet measured. To find out: Compare the seconds credited to a first create from a large image with a later create from the same image. |
| Billed separately | Data transfer is billed per GB crossing the datacenter boundary in either direction. No creation, snapshot or request charge is published on the pricing page. [^1] |
| Left out | Plan fees, the monthly included usage, Enterprise options such as active-CPU pricing, data transfer, snapshots and taxes. [^1] |
| Per-sandbox data | Partly. GET /v5/vms/{id} reports totalRunSeconds, createdAt and the allocated size, but no cost and no usage endpoint exists. The record is deleted with the VM, so it must be read after a pause and before the delete. [^4] |

## Not known yet

- Is Freestyle's invoiced charge for a VM equal to the calculated quantities at list rates? The measured account is on the Free plan, which bills nothing.
  - To find out: On a paid plan, run VMs of known run seconds and compare the invoice lines with the calculated figure.
- How does Freestyle round a run's seconds into totalRunSeconds? Credits differed from our wall times by under 1 s per run in both directions.
  - To find out: Run many short VMs with a known start and stop, and compare the credited seconds with the edges of the pause call.
- Is a VM's storage billed from createdAt, from its first boot, or from its first stop, and until when after a delete? No deleted-at time is stated.
  - To find out: On a paid plan, compare the invoiced storage hours of a VM kept for a known time with its createdAt and delete times.
- Do the pausing and starting states bill compute? Only a running VM is described as holding a compute reservation.
  - To find out: Compare the invoiced vCPU-hours of a VM paused and started repeatedly with totalRunSeconds.
- Does a resize change the seconds credited before it? The record holds one allocation, so earlier seconds would be priced at the new size.
  - To find out: Resize a VM between two runs and compare the invoice with the seconds at each size.

## Our measurements

- 2026-11-23: [The run-seconds record of a VM](evidence/2026-11-23-run-seconds.md). Two VMs on the Free plan, with seven runs of 3 to 31 s. totalRunSeconds read 0 during a first run, was credited at each pause, held through a 13 s pause, and the record answered 404 after the delete. Rounding was not determined. One team, one region, the default size.

## Price versions

- [`freestyle@2026-11-23`](../../src/sandbox_provider_pricing/providers/freestyle/prices/2026-11-23.yaml): from 2026-11-23, read 2026-11-23, in effect now.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/freestyle/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [freestyle.sh/docs/vms/pricing-and-limits](https://www.freestyle.sh/docs/vms/pricing-and-limits)
[^2]: [2026-11-23-run-seconds.md](evidence/2026-11-23-run-seconds.md#results)
[^3]: [2026-11-23-run-seconds.md](evidence/2026-11-23-run-seconds.md#limits)
[^4]: [2026-11-23-run-seconds.md](evidence/2026-11-23-run-seconds.md#verdict)
