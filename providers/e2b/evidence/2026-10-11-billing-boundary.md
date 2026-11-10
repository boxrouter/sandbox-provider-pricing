# Billing boundary against E2B lifecycle events

**Date:** 2026-10-11. **Provider:** E2B. **Result:** On five sandboxes of about 30 seconds, E2B's
`created` event fell inside each create call and its `killed` event inside each destroy call,
so the provider's events can mark the billing edges; this does not show that E2B bills from
those events, does not test pause, and does not compare against any billed figure.

## Question

Which moment starts and ends billing for one sandbox: the call we send, the call returning, or
the provider's own lifecycle events? E2B's billing page says compute is billed "per second ...
while your sandbox is running" and that billing "stops immediately" when a sandbox is paused,
killed or times out. It does not say where that clock starts during creation, so the check
compares E2B's event timestamps with our own call times.

## Method

- **Sandboxes:** five, each running about 30 seconds, created through BoxRouter's adapter for
  E2B on E2B templates:
  - sample 1: large (2 vCPU / 4 GiB), cold (first use by this account);
  - samples 2 and 3: the same large image, cached;
  - samples 4 and 5: E2B's default small template, cached.
- **What we did:** create, wait about 30 seconds, kill. No pause or resume.
- **Our times:** for each call, the moment it was sent and the moment it returned, from our own
  clock.
- **The provider's figures:** the `created` and `killed` lifecycle event timestamps for each
  sandbox from the events API (`GET /events/sandboxes/{id}`). These are E2B's timestamps. They
  were compared with our call times as `event - call edge`, in milliseconds. A negative value
  against a "returned" edge means the event came before the call returned. Event-derived running
  time is `killed - created`.
- **Event latency (separate run, same day):** two more sandboxes of 30 seconds. We read
  `GET /events/sandboxes/{id}` right after kill and again at intervals up to 300 seconds, and
  recorded which events were present.

## Results

Offsets are the provider event minus our call edge, in milliseconds.

| # | Image case | `created` − create sent | `created` − create returned | `killed` − destroy sent | `killed` − destroy returned |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | Cold large (2 vCPU / 4 GiB) | 9,697.302 | -38.560 | 106.311 | -36.105 |
| 2 | Cached large (2 vCPU / 4 GiB) | 682.715 | -269.080 | 108.679 | -36.492 |
| 3 | Cached large (2 vCPU / 4 GiB) | 654.452 | -34.051 | 108.577 | -36.048 |
| 4 | Small cached (E2B default) | 123.910 | -34.817 | 106.408 | -35.990 |
| 5 | Small cached (E2B default) | 149.382 | -131.242 | 106.319 | -36.321 |

- All five `created` events and all five `killed` events fell inside their own call windows
  (after the call was sent, before it returned).
- Create calls took 9.736 s (cold large), 0.689 to 0.952 s (cached large) and 0.159 to
  0.281 s (small cached).
- Event-derived running times were 31.096 to 36.443 s.

### Event latency

- `created` was present as soon as we read after the 30-second run. The events API answered
  404 until the first event existed, so a read right after create and kill can find nothing.
- `killed` was missing when we read at kill time. It appeared within 5 seconds for one
  sandbox and within 15 seconds for the other, and the events did not change through 300
  seconds.
- The timestamps are the true event times, not the time of arrival: `killed` for one sandbox was
  09:33:32.08 against our destroy call at 09:33:32.
- A reader right after kill therefore gets `created` only; the `killed` event needs at least
  15 seconds to be sure of.

## Verdict

- The provider's `created` event lands between create sent and create returned, and its
  `killed` event between destroy sent and destroy returned, for both a cold large image and
  cached images. The `created` event came 34 to 269 ms before the create call returned and
  after it was sent, by up to 9.7 s for the cold image. This supports using E2B's own event
  timestamps as the start and end of the billing clock, because they are consistent across the
  image cases.
- It is not proof that E2B bills from those events: no billed figure exists per sandbox to
  compare with (E2B shows the bill per account in its dashboard), so the check cannot rule out
  that billing starts earlier, for example when the image is loaded.
- Not settled: whether loading a cold image is billed (the cold create's `created` event came
  9.7 s after create was sent, so a billing start at create sent would include that load);
  whether pausing stops billing as documented; how long events are retained beyond the 300
  seconds read.

## Limits

- Five sandboxes of about 30 seconds, one account, one region, the plan not
  recorded. One cold large image only.
- Latency was measured on two sandboxes; the 5 and 15 second figures are the first reads where
  `killed` was present, not a distribution.
- Pause and resume were not run.
