# Beam list prices (2026-11-23)

Read from the live pages on 2026-11-23 (the price version `beam@2026-11-23` quotes them):

- https://www.beam.cloud/pricing: "Performance tier. Sandbox and VM prices are for 1 vCPU and 1 GiB of RAM."
  The CPU pricing tiers table lists, per vCPU-hour and per GiB-hour: Spot $0.0063 and $0.00135, Shared $0.011 and
  $0.0055, Performance $0.05 and $0.01. "New accounts default to Performance." Sandboxes: "Pay by the millisecond,
  only when the sandbox is running." Example: "A 2 vCPU / 8 GiB sandbox on Performance costs $0.18/hr, or $0.00005
  per second" (2 x 0.05 + 8 x 0.01 = 0.18).
- https://docs.beam.cloud/v2/resources/pricing-and-billing: tiers, "A workload keeps its tier's prices from its first
  run", waiting for a machine and pulling an image are not charged, storage "is not billed yet" with a planned
  $0.0001 per GB-hour and no free allowance.

Earlier research (battleships, 2026-09-28; sandbox page redesign, 2026-09-29) recorded $0.0675 per vCPU-hour and
$0.02304 per GiB-hour, quoted per physical core (2 vCPU); the current page is per vCPU with the rates above. The
June 2026 blog rates were higher again. The price version records only what the page says today.

## What Beam does not expose

No per-sandbox usage, billed duration or cost field was found in the Python SDK, the TypeScript SDK, the gateway
REST `GET /containers` object or the platform API (read 2026-11-23). The billing page points to the dashboard.
A sandbox's cost is therefore unknown to BoxRouter: list prices are never used to make one.
