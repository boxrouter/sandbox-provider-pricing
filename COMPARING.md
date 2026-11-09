# Comparing providers

Two providers can publish rates that look alike and still charge very different amounts for the
same work, because they meter different things. This page lists those differences, then quotes one
size on every provider. Each provider's page in `providers/<name>/` has the details and sources.

## What a CPU is

| Provider | CPU unit | Billed on |
| --- | --- | --- |
| Blaxel | Not metered separately | Included in the memory rate |
| Daytona | vCPU | The allocation, while running |
| E2B | vCPU | The allocation, while running |
| Modal | Physical core, which is 2 vCPUs | The larger of the request and the actual use, while running |
| Vercel | vCPU | Only while the CPU is busy; I/O wait is not billed |

A Modal rate per core is a rate per two vCPUs. Halve it before you compare it with a vCPU rate.

## Allocated, used, or the larger of the two

- Daytona, E2B and Vercel's memory bill the size you asked for, busy or not. The cost follows from
  the size and the time.
- Vercel's CPU is billed only while busy, so an idle sandbox pays for memory only. Only Vercel can
  report how busy a sandbox was.
- Modal bills the larger of request and use. A sandbox that uses more than it asked for pays for
  what it used, and Modal does not report use per sandbox.
- Blaxel bills memory only while the sandbox has an active connection. Without one the sandbox goes
  to standby, where its snapshot storage is billed instead. Wall-clock time overstates the cost of
  a mostly idle Blaxel sandbox; the [Blaxel page](providers/blaxel/README.md) has the measured
  standby delay.

## GB and GiB

A GiB is 7.4% larger than a GB. Daytona, E2B and Modal price memory per GiB. Blaxel and Vercel
price it per GB, and bill a 4 GiB (4,096 MiB) sandbox as 4 GB: Blaxel's per-sandbox costs confirm
this, and Vercel's own examples read it that way. Each price version records which reading it uses
(`size_per_unit`).

## When the clock runs

Providers differ in whether creating the sandbox and pulling its image is billed, in minimum
increments, and in what a paused or stopped sandbox pays. Vercel bills memory in one-minute
increments and Blaxel truncates to whole seconds. Daytona keeps charging for disk while stopped,
E2B charges nothing while paused, and Blaxel's standby bills snapshot storage but not memory. For a
short sandbox these rules can matter more than the rate.

## What else is on the bill

Disk, network egress, creation fees, snapshot and image storage, region multipliers, plan fees and
free credits all differ. Modal, for example, charges more when you pin a region. The costs in this
repository are list-price usage, before any credit, allowance, discount, commitment, plan fee or
tax.

## What the provider tells you afterwards

Blaxel and Daytona report what one sandbox cost. E2B and Vercel report usage or lifecycle events
that can be priced. Modal reports cost per App per hour, which gives a sandbox's cost only when the
App ran that sandbox alone. The label on every cost says which kind of figure it is
([METHOD.md](METHOD.md)).

## One hour at one size

Two vCPUs and 4 GiB of memory, running for one hour, at list price in the provider's base region,
with no disk, network or storage. These are rate-card quotes from
`sandbox_provider_pricing.calculator.per_hour` on each provider's newest price version, not the
cost of any sandbox. `make docs` regenerates the table.

<!-- generated:hourly -->
| Provider | One hour (USD) | Billed on | Price version |
| --- | ---: | --- | --- |
| Blaxel | 0 to 0.1656 | Memory only while in use | [`blaxel@2026-11-07-122300Z`](src/sandbox_provider_pricing/providers/blaxel/prices/2026-11-07-122300Z.yaml) |
| Boat | 0.018 | Flat per-size rate, not per vCPU or GiB | [`boat@2026-11-01-052001Z`](src/sandbox_provider_pricing/providers/boat/prices/2026-11-01-052001Z.yaml) |
| boxd | 0 to 0.15 | CPU and memory only while in use | [`boxd@2026-11-02-082924Z`](src/sandbox_provider_pricing/providers/boxd/prices/2026-11-02-082924Z.yaml) |
| Daytona | 0.1656 | CPU and memory as requested | [`daytona@2026-10-24-065001Z`](src/sandbox_provider_pricing/providers/daytona/prices/2026-10-24-065001Z.yaml) |
| E2B | 0.1656 | CPU and memory as requested | [`e2b@2026-10-31-015029Z`](src/sandbox_provider_pricing/providers/e2b/prices/2026-10-31-015029Z.yaml) |
| Modal | at least 0.23796 | CPU and memory at the larger of request and use | [`modal@2026-11-05-065701Z`](src/sandbox_provider_pricing/providers/modal/prices/2026-11-05-065701Z.yaml) |
| Vercel | 0.0848 to 0.3408 | CPU only while in use, memory as requested | [`vercel@2026-10-20-055631Z`](src/sandbox_provider_pricing/providers/vercel/prices/2026-10-20-055631Z.yaml) |
<!-- /generated:hourly -->

A range runs from no use to full use for the whole hour. Blaxel's low end is a sandbox in standby
all hour, and Vercel's is a sandbox whose CPU is never busy. Modal's figure prices the request; a
sandbox that uses more pays more. Daytona's disk, Vercel's creation fee and every provider's
storage and network charges are extra.
