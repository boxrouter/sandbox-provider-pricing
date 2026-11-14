# Idle time on a Superserve sandbox

**Date:** 2026-11-14. **Provider:** Superserve (one BoxRouter team, legacy pay-as-you-go catalog). **Result:** A sandbox
with no idle timeout and no activity stayed `active` and was billed at its full size for 8 min 14 s: nothing paused it and
nothing scaled it down. A sandbox created with `idle_timeout_seconds` 60 was paused by Superserve about 67 s after its last
command, and the team's meter stopped at that pause and stayed flat for the 43 s it was read afterwards.

## Question

Does Superserve bill an idle sandbox, or does it pause it, or scale it down, on its own? Its pricing page says "Pay only
while sandboxes are running", and its lifecycle page says an idle timeout pauses a sandbox "after this many seconds with no
activity" and that "by default, the idle timeout is unset, and the sandbox never pauses for being idle". The question is
what the meter does, not what the pages say.

## Method

- **Two sandboxes in turn**, created through the Python SDK 0.12.0 on the default template `superserve/base`, each with one
  command (`echo hi; free -m`) right after create and nothing after it. Script: `run.py` (key from Secrets Manager, never
  printed or written). Metadata `run=ss-pricing2-20261114T043245Z-a` and `-b`.
  - **A:** `timeout_seconds` 700 (a safety bound that did not expire) and no idle timeout or auto-delete. Left idle 8 min,
    then deleted.
  - **B:** `idle_timeout_seconds` 60 and `timeout_seconds` 300 (bound). Read every 10 s until paused, then for about 65 s
    more, then deleted.
- **Readings:** every 30 s (A) or 10 s (B): `GET /sandboxes/{id}` (status, `memory_mib`, `memory_max_mib`,
  `memory_current_mib`, `timeout_seconds`, `idle_timeout_seconds`), the team's cumulative usage
  (`GET /teams/{id}/billing/usage`: `vcpu_seconds`, `memory_mib_seconds`, `storage_mib_seconds`), the hourly series
  (`GET /billing/usage-series`) and the sandbox list. After each delete, `GET /activity` for the sandbox's rows.
- **Attribution.** `GET /sandboxes` listed no other sandbox from before A until 04:43:11, 12 s before B was deleted. The
  team's meter is therefore this sandbox's alone until then; readings after 04:43:11 are not used.
- **Cleanup.** `GET /sandboxes?metadata.run=<label>` with every non-deleted status returned 0 sandboxes for both labels.
- **Cost.** 562.8 s at 2 vCPU and 4 GiB at the list rates: $0.0259. The team's `current_charges_usd` rose $0.0264, the
  difference being another lane's sandbox at the end.

## Results

### A: no idle timeout, left idle 8 min

- `status` was `active` at all 17 readings, 04:32:46 to 04:40:59. The sandbox settings read back `timeout_seconds` 700,
  `idle_timeout_seconds` null, `auto_delete_seconds` null. The rows were `started` (04:32:47.380) and `deleted`
  (04:41:01.776): no pause row.
- The meter ran at the same rate throughout. Between readings 30.7 to 31.3 s apart, `vcpu_seconds` rose 1.985 to 2.019 per
  second and `memory_mib_seconds` 4,065 to 4,136 per second; per vCPU-second the memory was 2,048.0 MiB at every interval,
  which is 4,096 MiB at 2 vCPU. The first and last intervals ran no differently from the middle.
- Team meter, create to after the delete: 987.665 vCPU-s and 2,022,737 MiB-s, which is 493.83 s at 2 vCPU and 4,096 MiB.
  The rows span 494.40 s, 0.57 s (0.11%) more.
- **Memory size.** `memory_mib` 4096, `memory_max_mib` null, `memory_current_mib` null: the base template is a fixed size, so
  there is no live memory resizing to shrink. The billed memory stayed 4,096 MiB while the sandbox was idle (`free -m` inside
  showed 277 MiB used of 3,939 MiB).

### B: `idle_timeout_seconds` 60

| time UTC | what | team `vcpu_seconds` | sandbox |
| --- | --- | ---: | --- |
| 04:41:03.623 | the command returned (last activity) | | active |
| 04:42:07.763 | reading | 54,811.269 | active |
| 04:42:12.886 | `idle_paused` row (system event, no actor) | | |
| 04:42:18.468 | reading | 54,816.990 | **paused** |
| 04:42:29.142 | reading | 54,816.990 | paused |
| 04:42:50.629 | reading | 54,816.990 | paused |
| 04:43:01.352 | reading | 54,816.990 | paused |
| 04:43:11.999 | reading: another lane's sandbox has started | 54,818.145 | paused |

- Superserve paused it. The `idle_paused` row is 69.3 s after the command returned by our clock (the rows' clock can differ
  by about a second), inside the 60 s timeout plus the provider's timer tick of about 11.5 s. The meter's last increase put
  its stop about 67 s after the command.
- **The meter stopped at the pause.** `vcpu_seconds` and `memory_mib_seconds` were identical to the microsecond at four
  readings from 04:42:18 to 04:43:01 (42.9 s) while the sandbox was paused and no other sandbox existed.
  `storage_mib_seconds` stayed 0.
- Team meter, from the end of A to the pause: 137.927 vCPU-s and 282,474 MiB-s, which is 68.96 s at 2 vCPU and 4,096 MiB.
  The rows span 70.01 s (`started` 04:41:02.877 to `idle_paused` 04:42:12.886), 1.05 s (1.5%) more: the meter stopped before the
  row, as it did before the `timeout_paused` row in the [billing-boundary check](2026-11-13-billing-boundary.md).
- The `idle_paused` row is a lifecycle action not seen before. The billing-boundary check listed `started`, `paused`,
  `resumed`, `timeout_paused`, `deleted` and `auto_deleted`.

## Verdict

- **A running Superserve sandbox is billed at its full allocated size whether or not it is busy.** Left idle with no idle
  timeout, it stayed `active` and kept billing 2 vCPU and 4,096 MiB for 8 min 14 s. Superserve does not pause it, and
  does not shrink it: the base template has no live memory resizing.
- **Billing stops only at a pause.** With `idle_timeout_seconds` set, Superserve pauses the sandbox about a minute after its
  last activity and the meter stops there. Without it, the sandbox bills until something pauses or deletes it: an explicit
  pause, `timeout_seconds` (active time), or a delete. The defaults for `timeout_seconds` and `idle_timeout_seconds` are unset.
- A paused sandbox was billed nothing for compute or memory (42.9 s here; 30.956 s and 11 min 18 s in the earlier
  checks) and nothing for storage.

## Limits

- One team, one region, the default template, 2 vCPU and 4,096 MiB. One idle sandbox of 8 min 14 s and one idle-paused
  sandbox.
- Only `superserve/base` was tested. A template with `memory_max_mib` set can grow and shrink; whether its billed memory
  follows `memory_current_mib` when idle was not tested.
- Neither a plan default nor a template default for the timeouts is documented; the sandboxes read back null for both.
- The idle-pause timer was tested at 60 s only, once.
- The paused period was 42.9 s here; the storage side of long pauses is in the [paused-storage check](2026-11-13-paused-storage.md).
