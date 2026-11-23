# Cost through the adapter against the spend API and usage times rates

**Date:** 2026-11-23. **Provider:** Sail. **Result:** One 60 s Sailbox with a known workload, read through the adapter's `cost()`: the final cost, $0.000241857, equals Sail's own spend total for the Sailbox, and equals its usage seconds times Sail's published rates to within 0.4 nanodollars. Sail's dashboard was not read.

## Question

Does the figure the adapter reports (`reported`, one `machine` line) equal what Sail's spend API holds for the Sailbox, and does that figure equal Sail's usage times its published rates?

## Method

- One Sailbox of the adapter's default size (1 vCPU, 16 GiB memory limit), created through the adapter (`SailProvider.create`) at 09:00:08Z on a 5-minute lifetime and destroyed through it after 60 s.
- Workload through `SailProvider.run`: `dd` of 128 MiB to disk with `fsync`; a Python process holding 256 MiB of touched memory for 40 s; a shell loop keeping one core busy for 30 s (`timeout 30 sh -c 'while :; do :; done'`). The run took 41.0 s.
- After the destroy, every 5 s: the adapter's `cost()` and a direct `GET /sailboxes/spend?sailbox_id=&from=` (same window start) until `cost()` was `final` and the direct figure had not changed for 60 s. `COST_FINAL_WITHIN_S` was 600 s.
- Check: usage seconds times the rates the spend response states, against the spend total. The Sailbox id is redacted.

## Results

Readings after the destroy returned (readings where something changed, and the first final one):

| Seconds after the end | cost() status | cost() total (USD) | Direct spend total (nanos) |
| ---: | --- | ---: | ---: |
| 0.4 | accruing | None | None |
| 97.6 | accruing | 0.000241857 | 241857 |
| 609.9 | final | 0.000241857 | 241857 |

Final figures:

| | Value |
| --- | ---: |
| `cost()` total, final | 0.000241857 USD |
| Spend API `cost_usd_nanos` | 241857 |
| Equal | true |
| Running seconds | 58.000628456 |
| vCPU seconds (rate 4167 nanos) | 30.303124486 |
| Memory GiB seconds (rate 2222 nanos) | 46.06698763483634 |
| Disk GiB seconds (rate 194 nanos) | 68.16193914198661 |
| Usage times rates (nanos) | 241857.382 |
| Difference from the spend figure (nanos) | 0.382 |
| Creation count | 0 |

The 30 s busy loop is 30.3 vCPU seconds; the rest of a second is the other processes. Billed running seconds were 58.0 for a Sailbox that lived about 60 s from the create returning: Sail does not bill cold-start time.

## Verdict

The adapter's final cost is Sail's own figure, byte for byte, and Sail's figure is its used seconds times its published rates ($0.015 per vCPU-hour, $0.008 per GiB-hour of memory, $0.0007 per GiB-hour of disk) to rounding in whole nanodollars. The figure was partial or absent until the first batch (97.6 s after the end) and did not change afterwards.

## Limits

One Sailbox, one organization, creation fees waived (`creation_count` 0), so whether the creation charge is inside `cost_usd_nanos` on a paying organization is not shown. Sail's dashboard (app.sailresearch.com) needs a signed-in browser and was not read.
