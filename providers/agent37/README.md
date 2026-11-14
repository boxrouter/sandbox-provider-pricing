# Agent37

Agent37 costs are `reported`. The provider's own cost for the sandbox, matching list price.

Agent37 meters each instance per minute at monthly rates divided by 730 hours, and its usage report gives each instance's compute spend, deleted instances included. That spend matched list rates in our check and is labelled reported; managed services billed to the instance are left out.

## How the cost is worked out

Agent37's compute_micros for the instance, divided by one million. Check: billed minutes × (vCPUs × CPU rate + GB of RAM × memory rate) ÷ 43,800 for running minutes, plus GB of disk × disk rate ÷ 43,800 for every minute.

What holds it back: Nothing. A deleted instance's settled compute spend in Agent37's usage report is labelled reported; it matched list rates in our check.

What would improve it: Nothing. Until the adapter has read the instance as deleted and found it in the usage report, the cost is unknown.

## Rates

From [`agent37@2026-11-12`](../../src/sandbox_provider_pricing/providers/agent37/prices/2026-11-12.yaml), in effect from 2026-11-11, default class `default`.

| Meter | Rate | Billed on | Billed while |
| --- | --- | --- | --- |
| CPU | $0.80 per vCPU-month | size requested, in 60 s increments | running |
| Memory | $0.70 per GB-month | size requested, in 60 s increments | running |
| Disk | $0.09 per GB-month | size requested, in 60 s increments | running, paused, stopped |

## Billing rules

| Rule | Answer |
| --- | --- |
| Billed on | $0.80 per vCPU-month and $0.70 per GB-month of allocated RAM while running, plus $0.09 per GB-month of reserved disk in every state; a month is 730 hours, metered per minute. [^1] |
| Billing starts | When the instance first reaches running; nothing is debited at create. Measured, the first billed minute began at the instance's created second, before create returned. [^1][^2] |
| Billing ends | At delete, which settles the final minutes. Measured, the last part minute before delete was billed in full. [^1][^2] |
| Rounding | Each period is billed in whole minutes, rounded up, and the next state starts at the end of the last billed minute; each settled debit is a whole micro-dollar. [^1][^2] |
| Idle and paused | Running and the transitional states bill the full rate; sleeping, stopped and waking bill disk only. A stopped instance measured billed disk alone. A sleeper parked in cold storage bills its compressed bytes at a separate rate. [^1][^2] |
| Image pull | Not stated. The meter starts at running, so a create that fails costs nothing; two measured creates of the default template returned in under a second. [^1][^2] |
| Billed separately | Managed LLM, search and tool calls debit the same wallet per instance within a budget that defaults to $0. Performance instances bill compute at 4x and VM instances at 2.5x. Backups and egress are not priced on the pages checked. [^1][^3] |
| Left out | Managed LLM, search and tool spend (the instance's other usage fields), Performance instances, cold-storage time, backups, egress, the sign-up credit and top-ups. [^1][^3] |
| Per-sandbox data | Yes. GET /v1/usage lists each instance's spend in micro-dollars over up to 90 days, deleted ones included; compute lands within the hour and, measured, at delete. [^1][^2] |

## Not known yet

- Can a deleted instance's usage total change after it has been read?
  - To find out: Re-read deleted instances' totals over days; the 2026-11-11 and 2026-11-13 checks read them for an hour after the delete.
- Is GB in the RAM and disk rates 10^9 bytes or a GiB?
  - To find out: Ask Agent37 or compare a reported charge for a size whose GB and GiB figures differ in the micro-dollar.

## Our measurements

- 2026-11-11: [Usage report compute against list rates](evidence/2026-11-11-usage-vs-list-price.md). On two default instances (one running, one stopped part way), compute_micros equalled the billed minutes at list rates to the micro-dollar and was readable at delete. One account, one size, one region.
- 2026-11-13: [A VM instance's usage report compute against list rates](evidence/2026-11-13-vm-instance-usage.md). On one VM and one default instance, compute_micros equalled the billed minutes at list rates, the VM's CPU and RAM at 2.5 times, to the micro-dollar; the adapter's first read after the delete was already settled. One account, one size, one region.

## Price versions

- [`agent37@2026-11-12`](../../src/sandbox_provider_pricing/providers/agent37/prices/2026-11-12.yaml): from 2026-11-11, read 2026-11-12, in effect now.
- [`agent37@2026-11-11`](../../src/sandbox_provider_pricing/providers/agent37/prices/2026-11-11.yaml): from 2026-11-11, read 2026-11-11, replaced by `agent37@2026-11-12`.

This page is generated from [billing.yaml](../../src/sandbox_provider_pricing/providers/agent37/billing.yaml) and the price versions by `make docs`. Edit those, not this file.

[^1]: [agent37.com/docs/agents-api/billing](https://www.agent37.com/docs/agents-api/billing)
[^2]: [2026-11-11-usage-vs-list-price.md](evidence/2026-11-11-usage-vs-list-price.md#results)
[^3]: [agent37.com/docs/agents-api/budgets](https://www.agent37.com/docs/agents-api/budgets)
