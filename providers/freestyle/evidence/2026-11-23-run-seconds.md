# The run-seconds record a Freestyle VM keeps

**Date:** 2026-11-23. **Provider:** Freestyle (one team on the Free plan, default Ubuntu snapshot,
4 vCPU / 8 GiB memory / 32 GiB storage). **Result:** `GET /v5/vms/{id}` returns the VM's own
`totalRunSeconds` ("Seconds this VM has spent running, across every run it has ever had"), whole
seconds, credited when a run ends. It reads 0 for the whole first run and does not include a run
that is still going. The VM record is gone (404) after the delete, so the figure can be read
only while the VM exists. Freestyle has no per-VM cost or usage endpoint.

## Question

Can a per-VM cost be built from Freestyle's own records, without a clock of ours? The documented
billing (`https://www.freestyle.sh/docs/vms/pricing-and-limits`) says compute is metered per second
on the allocated vCPUs and memory while the VM runs, a paused VM bills only storage, and storage
bills for the time the VM is allocated. The page does not say where a consumer reads the seconds.

## Method

- Two VMs, created with `POST /v5/vms` (`firewall: {rules: []}` is required; `automaticRestart:
  false`, `autoDeleteSeconds: 900` as a safety net, a run id in `metadata`). Both took the default
  size (`resources`: cpu 4, memory 8192 MiB, storage 32768 MiB).
- VM 1: ran 31 s, paused, read three times over 13 s, then three more start/pause cycles of about
  2.4, 5.7 and 9.3 s with a read after each, a last start left running 6 s and read, then deleted
  while running. VM 2 (the sequence a capture before a delete uses): created, 20 s run, pause,
  resume, 10 s run, pause, read once, delete.
- Our times: each call's send and return time from our own clock (in the raw file). Provider
  figures: the VM's `state`, `totalRunSeconds`, `createdAt` and `updatedAt`.
- Everything was deleted by the script that created it; `GET /v5/vms` after each run listed none
  of these VMs. Raw answers: `raw/2026-11-23-run-seconds.json` (ids, addresses and the key are
  absent).

## Results

`updatedAt` moves on every state change. Wall time below is `updatedAt` at the start of a run to
`updatedAt` at its pause.

| Run | Wall (s) | `totalRunSeconds` before | after | Credited |
| --- | ---: | ---: | ---: | ---: |
| VM 1 run 1 | 31.30 | 0 | 31 | +31 |
| VM 1 run 2 | 3.08 | 31 | 34 | +3 |
| VM 1 run 3 | 6.37 | 34 | 40 | +6 |
| VM 1 run 4 | 10.30 | 40 | 50 | +10 |
| VM 1 run 5 (left running 6 s, deleted) | 6.28 | 50 | not read | not credited |
| VM 2 run 1 | 20.73 | 0 | 20 | +20 |
| VM 2 run 2 | 10.72 | 20 | 31 | +11 |

- While a VM runs, `totalRunSeconds` stays at the sum of its finished runs: it read 0 at 0, 15
  and 30 s into VM 1's first run, and 40 after 9.3 s of VM 1's run 4 until the pause credited it.
- A pause credits the run at once: the first read after each pause call already held the new total,
  and reads 3 s and 13 s later were unchanged.
- A paused VM's figure does not move (13 s of pause: no change).
- After the delete, `GET /v5/vms/{id}` answered 404 `NOT_FOUND`; the VM was gone from the list.
- `cpuTimeSeconds` stayed null; there is no started-at field, and `lastNetworkActivity` stayed null.
- `resources` gave the allocation (cpu, memory MiB, storage MiB) on every read.

## Verdict

`totalRunSeconds` is the provider's own record of a VM's running time, and a read taken after a
pause holds every finished run. A consumer that pauses the VM, reads it and then deletes gets the
whole running time from Freestyle's record; a read while the VM runs leaves out the current run,
and a delete while it runs loses it. Cost lines are then: vCPU-seconds (`totalRunSeconds` times
allocated vCPUs), GiB-seconds of memory (times allocated GiB), and GiB-seconds of storage for the
time from `createdAt` to the read.

## Limits

- Whole seconds only. Against our wall times the credits differ by up to about 1 s per run in both
  directions (VM 2 run 1 credited 20 for 20.73 s, run 2 credited 11 for 10.72 s), so Freestyle's
  rounding rule is not determined; the error is bounded by one second a run, about $0.00007 for
  the default size per run.
- Storage time ends at our read, not at the delete, because Freestyle states no deleted-at time;
  the figure leaves out the seconds between the read and the delete (1.2 s here).
- One team, the Free plan, one region, the default snapshot, no VM resized. A resize between runs
  is not covered: the record has one `resources` value, so seconds before a resize would be
  priced at the new size.
- Whether Freestyle's invoice equals these quantities at list rates is not measured: a Free
  account bills nothing.
