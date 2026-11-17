# What Modal bills for the cpu argument, and what a benchmark box cost

**Date:** 2026-11-16. **Provider:** Modal. **Result:** a sandbox created with `cpu=N` is billed N cores at
Modal's core rate and shows N CPUs to its guest, so a size that asks for N vCPUs and is created with
`cpu=N` costs N cores, not N / 2. The check could not settle whether a size request should mean a CPU the
guest sees or a hardware thread (two per core), which is a decision about the request, not a billing fact.

## Question

Modal's pages say the `cpu` argument is physical cores and that one core is two vCPUs as AWS or GCP count
them. The price version priced a requested vCPU as half a core. When a sandbox is created with `cpu=N`
for a size that asks for N vCPUs, which price does Modal's own bill show: N cores or N / 2 cores? The
documentation gives the definition of a core, not what the guest sees or what the bill adds up to.

## Method

- Sandboxes: five ephemeral Apps in an internal workspace, one sandbox each, Modal's slim Debian image,
  4096 MiB memory, no region set, at most 60 s, all ended, no tasks left running. Two sizes: `cpu=1`
  and `cpu=2`. SDK 1.6.1.
- What we did: `nproc` and `/proc/cpuinfo` read in each guest; one, two and four busy loops timed in 3 s
  windows; each sandbox held to the same lifetime (60.4 s) so the bill rows compare.
- The provider's figures: the workspace billing report at hourly resolution (`modal.Workspace.billing.report`),
  read about eight minutes after the sandboxes ended; the rows of the two sandboxes are compared.
- Benchmark sandboxes: 520 published benchmark trials on Modal (the gVisor class), 320 requested at 4 vCPU
  and 8 GiB and 200 at 2 vCPU and 4 GiB. Each trial's dollars are Modal's per-App bill row (see the
  per-App check below); the implied hourly price is the trial's dollars over Modal's own
  `created_at` to `finished_at`. The raw rows are retained by the maintainers.

## Results

| `cpu` | `nproc` | Busy loops 1 / 2 / 4, relative speed | Billed for 60.4 s |
| ---: | ---: | --- | ---: |
| 1 | 1 | 1.0 / 2.0 / 4.0 | $0.00396579 |
| 2 | 2 | 1.0 / 2.0 / 4.0 | $0.00633074 |

The 60.4 s bill differs by $0.00236495 for one extra core, which is $0.1409 per core-hour. The published
rate is $0.00003942 per core-second, which is $0.14191 per core-hour, so the measured figure is 0.7% below it
(no region multiplier applies, as no region was set). The memory part (4 GiB, 60 s) accounts for the rest of
each bill. `/proc/cpuinfo` lists two processors on both sizes. No cgroup quota file exists inside the sandbox,
so the CPU limit is not visible there; the busy loops scaled with the number of loops up to four on both
sizes.

Benchmark sandboxes, implied price per hour (median, 5th to 95th percentile):

| Requested size | Sandboxes | Implied $ per hour | 4 cores or 2 cores at the `us` rate | Half of it |
| --- | ---: | ---: | ---: | ---: |
| 4 vCPU, 8 GiB | 320 | 0.858 (0.823 to 0.872) | 0.8737 (cpu=4) | 0.5473 |
| 2 vCPU, 4 GiB | 200 | 0.395 (0.104 to 0.435) | 0.4369 (cpu=2) | 0.2737 |

The 325 sandboxes of the per-App check (`2026-10-23-per-app-bill.md`) were created with `cpu=(2,2)`, 4096 MiB
and the `us` region, and the bill sat a median 3.7% below 2 cores' list price over their lifetime
(cost = lifetime x $0.00012135 per second), so a two-core price was already the one that matched.

## Verdict

Modal bills `cpu=N` as N physical cores, and the sandbox then shows N CPUs. The benchmark's 4 vCPU
sandboxes billed 98% of four cores' price and 157% of two cores' price. The 2 vCPU sandboxes' median is
10% below two cores' price with a long low tail (5th percentile 0.104), which the lifetimes explain only
in part; their upper end is 0.4% below it. A price that counts a requested vCPU as half a core is 37%
below what these sandboxes cost. This does not settle what "vCPU" means in a size request.

## Limits

Two sandboxes per size in the live check; one base image; one region multiplier (`us`); a 60 s lifetime.
The benchmark sandboxes were not made to measure billing, so their lifetimes carry the provider's create
and teardown. Whether the guest's CPUs are full cores or threads of a core was not measured: the busy-loop
test shows scaling with the number of loops, not the speed of one loop.
