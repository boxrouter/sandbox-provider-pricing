# Billing boundary against Daytona's billed periods

**Date:** 2026-10-11. **Provider:** Daytona. **Result:** On seven sandboxes (eleven billed
periods), Daytona's first billed period began 14 to 86 ms before the create call returned and
its last ended 28 to 68 ms after the destroy call was sent, including after a create that took
27.9 seconds to build or pull an image; the check covers one organization, two sizes and
container sandboxes only, and cannot say whether every cold image is unbilled.

## Question

Which moment starts and ends billing for one Daytona sandbox: the call we send, the call
returning, or Daytona's own record? Daytona's billing page says "Creating, Starting, Stopping
and Pausing are billed the same as started", which suggests the time spent creating could be
billed, and says nothing about image pulls. Daytona's per-sandbox billed periods let us compare
its own start and end with our call times, and the stop-and-start cases test what a billed
period looks like while a sandbox is stopped.

## Method

- **Sandboxes:** seven, created through BoxRouter's adapter for Daytona on a Daytona
  organization used for testing. None was created as a VM, so all seven are Linux containers,
  Daytona's default ("Sandboxes run as Linux containers by default",
  <https://www.daytona.io/docs/en/sandboxes/>). Daytona's own pause is "Supported for VM
  sandboxes only" (<https://www.daytona.io/docs/en/billing/>), so BoxRouter's adapter carries
  out a pause with Daytona's stop call and a resume with its start call. The "pause" and
  "resume" below are those BoxRouter calls, and the sandbox was in Daytona's stopped state
  between them:
  - two "long cached" sandboxes of 1 vCPU / 1 GiB / 3 GiB with the standard image already
    cached by the account, running 10 minutes;
  - three "paused cached" sandboxes of the same size and image: one ran about 60 seconds
    and was destroyed (no pause was recorded for it); two ran 60 seconds, were paused (stopped)
    for about 5 minutes, resumed (started), ran 60 more seconds and were destroyed;
  - two "cold sized" sandboxes of 2 vCPU / 4 GiB / 10 GiB created from an image through
    Daytona's image path, each destroyed after a few seconds. The first create took 27,915 ms,
    long enough to be an image build or pull; the run record does not say which. The second
    took 805 ms, so it was probably served from Daytona's cache; only the first is a long create.
- **What we did:** create, wait, optionally pause and resume, destroy, using Daytona's
  Python SDK as driven by the adapter. One earlier pause attempt was refused by BoxRouter before
  reaching Daytona (its request lacked a required option) and its sandbox was destroyed; it is
  excluded.
- **Our times:** for every call, the moment it was sent and the moment it returned, from our own
  clock. The first paused sandbox's saved record has no pause or resume call times, so it can
  only be compared with its create and destroy calls.
- **The provider's figures:** each sandbox's billed periods (`startAt`, `endAt`, `price`) from
  Daytona's analytics API, read after the runs (all seven reads succeeded). Offsets are Daytona's
  timestamp minus our call time, in milliseconds; negative means Daytona's timestamp is before
  our call edge.

## Results

Offsets are the first billed period's start and the last billed period's end against our call
edges. Period lengths are in milliseconds with CPU / memory / disk in GiB reserved.

| # | Case | Billed periods (ms; vCPU / GiB memory / GiB disk) | Billed (s) | Start − create sent (ms) | Start − create returned (ms) | End − destroy sent (ms) | End − destroy returned (ms) | Total price (USD) |
| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Long, cached | 600,112 (1 / 1 / 3) | 600.112 | +1,030 | −61 | +51 | −717 | 0.01115608208 |
| 2 | Long, cached | 600,117 (1 / 1 / 3) | 600.117 | +724 | −50 | +67 | −792 | 0.01115617503 |
| 3 | Short, cached | 60,125 (1 / 1 / 3) | 60.125 | +5,269 | −86 | +39 | −613 | 0.00111772375 |
| 4 | Stopped and started | 60,106 (1 / 1 / 3); 301,388 (0 / 0 / 3); 60,316 (1 / 1 / 3) | 421.810 | +561 | −49 | +65 | −593 | 0.00226576990 |
| 5 | Stopped and started | 60,150 (1 / 1 / 3); 302,731 (0 / 0 / 3); 60,267 (1 / 1 / 3) | 423.148 | +669 | −57 | +28 | −696 | 0.00226579782 |
| 6 | Cold sized | 247 (2 / 4 / 10) | 0.247 | +27,901 | −14 | +61 | −649 | 0.00001143610 |
| 7 | Cold sized | 299 (2 / 4 / 10) | 0.299 | +785 | −20 | +68 | −603 | 0.00001384370 |

Reading the first two columns of offsets: the billed start lies inside the create call (after
create sent, before create returned) in every row, and the billed end lies inside the destroy
call (after destroy sent, before it returned) in every row.

Pause and resume transitions in rows 4 and 5, with each period's offsets against the matching
call (milliseconds; negative is before the edge):

| # | Running period 1 starts | Running period 1 ends | Stopped period starts | Stopped period ends | Running period 2 starts | Running period 2 ends |
| ---: | --- | --- | --- | --- | --- | --- |
| 4 | 49 before create returned | 57 after pause sent | 61 after pause sent | 17 before resume returned | 13 before resume returned | 65 after destroy sent |
| 5 | 57 before create returned | 93 after pause sent | 98 after pause sent | 19 before resume returned | 13 before resume returned | 28 after destroy sent |

The stopped periods report 0 vCPU, 0 memory and 3 GiB disk.

### Price against list rates

Each total price equals the billed seconds multiplied by the list rates of the 2026-10-11
price version, to the last digit shown: $0.000014 per vCPU-second, $0.0000045 per GiB-second of
memory and $0.00000003 per GiB-second of disk. Disk is charged in full (3 GiB in rows 1 to 5,
10 GiB in rows 6 and 7), with no deduction for the "first 5 GiB free" allowance; stopped periods
are charged for disk alone (301.388 s at 3 GiB gives $0.0000271). The recalculation was done for
this file from the table above and matches all seven totals.

### Image cache measurements (separate runs, 2026-10-11)

These measure how long the create call takes, not what is billed. A create that gives a size
builds the standard image through Daytona's image path; a create without a size uses a
preinstalled snapshot and stays near 0.7 s.

| Case | Create time |
| --- | ---: |
| Cold build (fresh instruction directly after `FROM`, so every layer rebuilds), 2 vCPU / 4 GiB | 25.633 s |
| Same image straight after, 4 / 8 and 2 / 4 | 0.869 s and 0.831 s |
| Last layer changed only | 0.940 s |
| Cache probe, 1 hour after the first create | 21.7 s (miss; 1.1 s at the start) |
| Cache probe, 6 hours after | 0.9 s (hit) |
| Cache probe, 24 hours after | not recorded |

The cache does not depend on CPU or memory size. It is not a simple expiry clock, and the
one-hour miss is unexplained.

## Verdict

- Billing starts at about the moment the create call returns: in all seven sandboxes Daytona's
  first billed period began 14 to 86 ms before create returned, and inside the create call. It
  ends at about the moment the destroy call is sent: the last period ended 28 to 68 ms after
  destroy was sent, and before it returned. The checked boundary is therefore create returned to
  destroy sent, which is the setting in `billing.yaml`.
- The 27.9-second create in row 6 was not billed: the billed period began 14 ms before create
  returned, 27,901 ms after create was sent. This supports the boundary for one genuinely
  slow image build or pull. Daytona's billing page says creating is billed like started, and it
  does not mention image pulls or builds, so this is a measurement, not a published rule.
- Stopped time is billed as disk only (0 vCPU and 0 memory, 3 GiB), as Daytona's billing page
  says for stopped sandboxes, and the three periods around a stop join to within about 100 ms.
- Each reported total price is reproduced exactly by the list rates applied to the billed
  seconds, for running and stopped periods alike.
- It does not settle whether other cold images, other sizes, other regions, paused (VM) or
  archived sandboxes, or sandboxes that run through an error would be billed the same way. It does not
  establish a pause transition for row 3. It does not show how a late-arriving period would be
  reported.

## Limits

- Seven container sandboxes on one organization, in one region, and two sizes. Only one create
  was a long image build or pull; the other "cold sized" create took 805 ms.
- The offsets of a few tens of milliseconds are measured against our clock and call times, so
  they include network and clock error of the same order and are not Daytona's exact edges.
- In the [price comparison](2026-10-05-reported-vs-list-price.md), our calculation over our own
  times was 1.06% to 1.80% below Daytona's price on 5-second sandboxes; the offsets here are the
  same kind of difference.
- Row 3's create call took about 5.4 seconds (start 5,269 ms after create sent); the cause is
  not recorded.
- Daytona's paused state (VM sandboxes only) and archived state were not tested.
- The 24-hour image cache sample was not recorded.
