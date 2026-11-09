# Session start and stop times against our call edges

**Date:** 2026-10-11. **Provider:** Vercel. **Result:** On five sandbox sessions of about 30
seconds, Vercel's session `startedAt` fell inside each create call and `stoppedAt` fell before
each destroy call was sent, and `duration` equalled `stoppedAt − startedAt` to the millisecond
in all five; the check did not read any invoice or billing export, so it does not show which
moment Vercel bills memory from.

## Question

Which moment starts and ends the billed memory clock for one sandbox: the call we send, the
call returning, or the session times Vercel reports? The pricing page says provisioned memory
is "the memory allocated to your sandbox (in GB) multiplied by the time it runs (in hours)" and
"billed in 1 minute minimum increments", and that active CPU excludes time "waiting for I/O"
([pricing](https://vercel.com/docs/sandbox/pricing)). It does not say where the memory clock
starts during creation or where it stops. The session record carries `startedAt`, `stoppedAt`
and `duration`
([Get a session](https://vercel.com/docs/rest-api/sandboxes/get-a-session)), so this check
compares those times with our own call times. It is a comparison of Vercel's session times with
our clock, not a comparison with a bill.

## Method

- **Sandboxes:** five sequential sessions, each about 30 seconds, 1 vCPU and 2 GiB of memory,
  with a 180-second time limit, created through BoxRouter's adapter for Vercel (adapter
  version not recorded). Trials 1 and 4 used the image configured for the adapter's standard
  environment (first use by this account, then a repeat); trials 2, 3 and 5 used Vercel's
  managed image `vercel/sandbox/universal`. Vercel does not expose whether an image was cached,
  so these are setup classes, not observed cache misses and hits. Region not recorded.
- **What we did:** create, wait about 30 seconds, ask for a clean stop (a pause request), read
  the session record from the API, then delete the sandbox. The session record was read before
  the delete because the session figures are available only after a successful stop
  (see [Limits](#limits)). After cleanup all five sandboxes were confirmed absent (HTTP 404).
- **Our times:** for the create call and the destroy call, the moment each was sent and the
  moment each returned, from our own clock.
- **The provider's figures:** per session, `startedAt`, `stoppedAt` and `duration`, as returned
  by the session record. Offsets below are the provider time minus our call edge, in rounded
  milliseconds. A negative value against a "returned" edge means the provider time came before
  that call returned; a negative `stoppedAt` offset means Vercel's `stoppedAt` came before our
  destroy call.

## Results

| Trial | Image setup | `startedAt` − create sent (ms) | `startedAt` − create returned (ms) | `stoppedAt` − destroy sent (ms) | `stoppedAt` − destroy returned (ms) | `duration` (ms) | `duration` − (`stoppedAt` − `startedAt`) (ms) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | Standard, first use | +366 | −923 | −822 | −1,131 | 32,668 | 0 |
| 2 | Universal | +114 | −149 | −1,659 | −1,938 | 35,024 | 0 |
| 3 | Universal | +119 | −99 | −1,171 | −1,771 | 33,944 | 0 |
| 4 | Standard, repeat | +116 | −688 | −904 | −1,703 | 32,324 | 0 |
| 5 | Universal | +195 | −116 | −904 | −1,220 | 34,777 | 0 |

Derived from the offsets above (returned − sent), for reading the table:

| Trial | Create call, sent to returned (ms) | Destroy call, sent to returned (ms) |
| ---: | ---: | ---: |
| 1 | 1,289 | 309 |
| 2 | 263 | 279 |
| 3 | 218 | 600 |
| 4 | 804 | 799 |
| 5 | 311 | 316 |

Other observations:

- In all five samples `startedAt` fell between create sent and create returned.
- In all five samples `duration` equalled `stoppedAt − startedAt` to the millisecond.
- `stoppedAt` followed our explicit pause request by 1,635 to 4,873 ms and preceded that
  request's return by 558 to 1,460 ms. It therefore preceded destroy sent by 822 to 1,659 ms.

## Verdict

Supported: Vercel's `startedAt` lies inside the create call, and `duration` is exactly
`stoppedAt − startedAt`, in five of five sessions, for two image setups. Reading the session
record after a clean stop and before deleting the sandbox gives these times.

Not supported: any claim about the billed memory interval. The check read no invoice, billing
charge or other billed figure, so it cannot say whether Vercel bills memory from `startedAt`
to `stoppedAt`, from `duration`, or from some other edge such as create sent or destroy
returned. The `stoppedAt` times here locate a clean stop around our pause request; they say
nothing about where a sandbox that is simply deleted, or stopped by timeout, would end. The
boundary therefore stays recorded as unchecked.

What would settle it: compare a sandbox's billed provisioned-memory quantity (from the billing
charges API, which reports per project per day) against its `duration`, with sandboxes long
enough that the 1-minute increment does not dominate, and in a project that runs nothing else
on the day compared.

## Limits

- Five sessions, about 30 seconds each, one size (1 vCPU / 2 GiB), run once. At that length the
  1-minute minimum increment would hide small differences in the edges.
- Image cases: the first-use result is one sample (trial 1, which also had the longest create
  call). A large custom image on first pull was not tested.
- Only sessions that stopped cleanly were read. Vercel documents the active CPU and network
  transfer figures as available only after a successful stop
  ([Get a session](https://vercel.com/docs/rest-api/sandboxes/get-a-session)); behaviour for
  timeouts, crashes and failed stops was not tested. `activeCpuDurationMs` and
  `networkTransfer` were not compared with anything here.
- Whether the clean stop also created a snapshot, and so started snapshot storage, was not
  recorded. Vercel's current documentation says sandboxes are persistent by default and
  snapshot on stop
  ([Persistence](https://vercel.com/docs/sandbox/concepts/persistent-sandboxes)). The snapshot
  size is not reported by the session record.
- The account's plan was not recorded.
