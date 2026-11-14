# A VM instance's usage report compute against list rates

**Date:** 2026-11-13. **Provider:** Agent37. **Result:** For one VM instance and one default
instance, the usage report's `compute_micros` equalled the billed minutes at the list rates,
with the VM's CPU and RAM at 2.5 times the default rates and its disk at the default rate,
rounded to a whole micro-dollar. Adapter-agent37's own cost reader reported both figures as
settled at its first read after the delete, and they did not change in the hour of reads after
it.

## Question

The 2026-11-11 check measured default instances only. Agent37's billing page says a VM
instance's "compute is 2.5x the default rate, and disk is unchanged". Is a VM instance's
per-instance figure in `GET /v1/usage` that rate applied to its billed minutes? And does the
current adapter (`adapter-agent37` 0.1.2 and later, which reports a deleted instance's cost at
its first read after `GET /v1/instances/{id}` answers `404`) report a settled figure at that
first read?

## Method

- Instances: two, created with `POST /v1/instances` and the body adapter-agent37 sends for a
  2 vCPU / 4 GB create (`resources: {cpu: 2, memory: 4}`, no disk):
  - default: template `agent37-base`, `mount_path: /mnt/agent37-disk`; Agent37 answered type
    `default`, region `us`, 2 vCPU, 4 GB RAM, 4 GB disk;
  - VM: template `agent37-ubuntu`, `type: vm`; Agent37 answered type `vm`, region `us`,
    2 vCPU, 4 GB RAM, 12 GB disk (the VM template's default).
  Both creates answered `status: running`.
- What we did: both instances ran until they were deleted by id about four minutes later.
- Our times: every call's send and return on our clock (UTC), below.
- The provider's figures: adapter-agent37's own cost reader (`provider_reports.aread_cost`,
  `adapter-agent37` 0.1.21) once while the instances ran, then 60 s, 5, 15,
  31 and 60 minutes after the deletes. The 30-minute read timed out on our side and was taken
  again a minute later. Integer micro-dollars; nothing converted.
- List rates (price version `agent37@2026-11-12`): $0.80 per vCPU-month, $0.70 per GB-month of
  RAM, $0.09 per GB-month of disk; the VM class's CPU and RAM at 2.5 times those; a month is
  730 hours, so a minute is 1/43,800 of a month. A running minute is:
  - default, 2 vCPU / 4 GB / 4 GB disk: (2 × 0.80 + 4 × 0.70 + 4 × 0.09) / 43,800 = $4.76 /
    43,800 = 108.6758 micro-dollars;
  - VM, 2 vCPU / 4 GB / 12 GB disk: (2.5 × (2 × 0.80 + 4 × 0.70) + 12 × 0.09) / 43,800 =
    $12.08 / 43,800 = 275.7991 micro-dollars.

Our calls (UTC):

| Call | Sent | Returned |
| --- | --- | --- |
| Create default (`h1g2aj3uhd`) | 21:28:18.695 | 21:28:19.815 |
| Create VM (`41wc7mgvwi`) | 21:28:19.815 | 21:28:20.828 |
| Delete default | 21:32:23.268 | 21:32:23.626 |
| Delete VM | 21:32:23.626 | 21:32:23.935 |
| Get default, VM | 21:32:23.935 | 21:32:24.276 (both `404`) |

The default instance's `created` was 21:28:19 and the VM's 21:28:20.

## Results

| Instance | Life (`created` to delete returned) | `awake_minutes` | Billed minutes | List price (micro-dollars) | `compute_micros` | `total_micros` |
| --- | ---: | ---: | --- | ---: | ---: | ---: |
| default | 4 min 4.6 s | 5 | 5 running | 5 × 108.6758 = 543.38 | 543 | 543 |
| VM | 4 min 3.9 s | 5 | 5 running | 5 × 275.7991 = 1378.99 | 1379 | 1379 |

- Each instance's 4 minutes and 4 seconds were billed as 5 minutes: the part minute before the
  delete was billed in full, as on 2026-11-11.
- The VM's figure is its CPU and RAM at 2.5 times the default rates plus its 12 GB of disk at
  the default rate. At the default rates for all three it would have been 5 × 125.1142 = 625.57
  micro-dollars; at 2.5 times for disk too, 5 × 312.7854 = 1563.93.
- While the instances ran, the usage report did not list them yet, and the reader answered
  `unknown` (`pending`) for both. That read is the fixture `pending`.
- The first read after the deletes (60 s after) answered `available` with the totals above. That
  read is the fixture `best` (default) and `vm`. The reads 5, 15, 31 and 60 minutes after the
  deletes returned the same totals, all `available`.
- Neither instance had managed-service spend: `total_micros` equalled `compute_micros`.

## Verdict

A VM instance's per-instance `compute_micros` is the list price of its billed minutes at the VM
rates, to the micro-dollar, as a default instance's is at the default rates. Both are labelled
`reported`, and the adapter's first read after the delete is already the settled figure.

This does not settle how long a deleted instance's total can still change beyond the hour read
here, whether rates on a discounted account are reported at list, or whether GB means GiB: the
report prices the size as Agent37 states it, so this check cannot tell them apart.

## Limits

One instance of each type, one size (2 vCPU / 4 GB), region `us`, one list-rate account, one
day, under five minutes each. Performance instances, sleeping and waking, cold storage and
instances that span a UTC day boundary or an hourly settlement were not measured.
