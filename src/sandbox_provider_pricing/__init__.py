# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Price sandbox usage from provider records, bundled billing rules and dated list-price versions.

- `price(evidence)`: the cost of one sandbox, labelled `reported`, `calculated` or `unknown`.
- `cost(usage, version)`: one usage document rated at one price version.
- `reproduce(result)`: re-rate a stored result with the price version it recorded.
- `record_evidence(record)`: the evidence for `price()` from what a consumer stored about a sandbox.
- `region_name(region, provider)`: a region without our provider prefix, as `record_evidence` does.
- `merge_reports(reads)`: several reads of one sandbox's Core reports, as one envelope.
- `compose(results)`: combine the results for the resources of one sandbox, or for several
  sandboxes, keeping each one.
- `next_read(result, ended_at, now)`: when to read the provider's records again, or None.
- `explain(result)`: a result's working as display text, each number with its source.
- `cost_method(provider, version)`: the cost method as data, as `cost-method.json` holds it.
- `reservation_quote(version, size, duration_seconds)`: the ceiling for a reservation, at full use.
- `lifecycle_quote(version, size, periods)`: a conditional quote for supplied lifecycle demand.
- `per_hour(version, size)`: the hourly rate of a sandbox that keeps running.
- `hourly(provider, size)`: that hourly rate with its published basis.
- `build_price_sheet()`: every provider's hourly rate at a list of (vCPU, GiB) sizes.
- `billing(provider)`: a provider's billing rules.
- `revisit(provider)`: a provider's policy for re-reading its records.
- `seed_versions()`: every bundled price version.
- `latest_version(provider)` and `price_version(provider, at)`: a provider's newest price version,
  and the one in effect at a time.
- `find_class(version, name)` and `covered_classes(price_class)`: a price version's class by name,
  and the spec classes a price class covers.
- `TIME_POINTS`: the time points the evidence schema allows.
- `LifecyclePeriod`, `LifecycleQuote`, `ReservationQuote`, `RevisitPolicy` and `TimeValue`:
  the types those functions take and return.
"""

from sandbox_provider_pricing.calculator import cost, find_class, per_hour
from sandbox_provider_pricing.calculator.documents import covered_classes
from sandbox_provider_pricing.compose import compose
from sandbox_provider_pricing.cost_method import cost_method
from sandbox_provider_pricing.evidence import TIME_POINTS
from sandbox_provider_pricing.explain import explain
from sandbox_provider_pricing.lifecycle import LifecyclePeriod, LifecycleQuote, lifecycle_quote
from sandbox_provider_pricing.price import hourly, price, reproduce
from sandbox_provider_pricing.price_sheet import build_price_sheet
from sandbox_provider_pricing.providers import billing
from sandbox_provider_pricing.read_time import READ_TIME_CONTRACT, READ_TIME_PATHS, settles_after
from sandbox_provider_pricing.reads import next_read
from sandbox_provider_pricing.record import merge_reports, record_evidence, region_name
from sandbox_provider_pricing.reservation import ReservationQuote, reservation_quote
from sandbox_provider_pricing.revisit import RevisitPolicy, revisit
from sandbox_provider_pricing.types import TimeValue
from sandbox_provider_pricing.versions import latest_version, price_version, seed_versions

__all__ = [
    "READ_TIME_CONTRACT",
    "READ_TIME_PATHS",
    "TIME_POINTS",
    "LifecyclePeriod",
    "LifecycleQuote",
    "ReservationQuote",
    "RevisitPolicy",
    "TimeValue",
    "billing",
    "build_price_sheet",
    "compose",
    "cost",
    "cost_method",
    "covered_classes",
    "explain",
    "find_class",
    "hourly",
    "lifecycle_quote",
    "latest_version",
    "merge_reports",
    "next_read",
    "per_hour",
    "price",
    "price_version",
    "record_evidence",
    "region_name",
    "reproduce",
    "reservation_quote",
    "revisit",
    "seed_versions",
    "settles_after",
]
