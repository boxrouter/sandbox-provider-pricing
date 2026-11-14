# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Provider lifecycle times and usage; call clocks remain diagnostic evidence only."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sandbox_provider_pricing._util import MIB_PER_GIB, parse_time
from sandbox_provider_pricing.evidence import core_report, validate_evidence
from sandbox_provider_pricing.types import BillableUsage, Document, JsonObject, TimeValue
from sandbox_provider_pricing.versions import find_class, price_version

STARTS = ("created", "started", "resumed", "billed_start")
ENDS = ("paused", "stopped", "ended", "billed_end")
#: How far a cost report's periods, and the gaps between them, may be from the sandbox's own times.
COVERAGE_EDGE_S = 60
REPORTED_WITHOUT_SECONDS = (
    "No billed seconds for this sandbox: the provider reports its cost instead."
)


def parse_datetime(value: str | None) -> datetime | None:
    return None if value is None else parse_time(value)


def utc_text(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def observation(evidence: Document, as_of: str | None) -> str:
    if as_of is not None:
        return as_of
    facts = [
        edge
        for call in evidence["calls"]
        for edge in (call.get("sent_at"), call.get("returned_at"))
    ]
    facts += [time["at"] for time in evidence["provider_times"]]
    facts += [evidence.get(name) for name in ("last_seen_alive", "noticed_gone", "deadline")]
    facts += [{"value": record["read_at"]} for record in evidence["provider_records"]]
    found = [parse_datetime(fact.get("value")) for fact in facts if fact and fact.get("value")]
    if not found:
        raise ValueError("as_of is required when evidence has no observation time")
    return utc_text(max(at for at in found if at is not None)) or ""


def revisit_end(evidence: Document) -> datetime | None:
    """End observation for scheduling record reads only; never used to price usage."""
    facts = [time["at"] for time in evidence["provider_times"] if time["kind"] in ENDS]
    facts += [
        call.get("returned_at")
        for call in evidence["calls"]
        if call["name"] == "destroy" and call["outcome"] == "returned"
    ]
    facts += [evidence.get("noticed_gone"), evidence.get("deadline")]
    found = [parse_datetime(fact.get("value")) for fact in facts if fact and fact.get("value")]
    return max((at for at in found if at is not None), default=None)


def unavailable(result: BillableUsage, reason: str) -> BillableUsage:
    """Keep missing provider evidence explicit in reproducible usage."""
    for usage in (result["low"], result["high"]):
        usage["intervals"] = [
            {
                "state": "running",
                "seconds": None,
                "source": "unknown",
                "observed_at": usage["started"]["observed_at"],
                "how": reason,
            }
        ]
    return result


def default_billable(evidence: Document, *, as_of: str | None = None) -> BillableUsage:
    """Build intervals exclusively from provider lifecycle events, never from call edges."""
    validate_evidence(evidence)
    observed_at = observation(evidence, as_of)
    start, end, intervals = _provider_timeline(evidence, observed_at)
    base = _usage_base(evidence, start, observed_at, intervals)
    result: BillableUsage = {
        "low": dict(base),
        "high": dict(base),
        "times": {"start": start, "end": end},
        "reported": None,
    }
    if not intervals:
        unavailable(result, "Waiting for the provider's lifecycle record.")
    return result


def _usage_base(
    evidence: Document, start: TimeValue, observed_at: str, intervals: list[JsonObject]
) -> JsonObject:
    requested = evidence["requested"]
    size = {
        key: requested[key]
        for key in ("cpu", "memory_mib", "disk_mib", "gpu", "gpu_model")
        if requested.get(key) is not None
    }
    base = {
        "provider": evidence["provider"],
        "started": {
            "at": utc_text(start.value),
            "source": start.source,
            "observed_at": observed_at,
            "how": start.how,
        },
        "region": {
            "name": requested.get("region"),
            "source": "recorded" if requested.get("region") is not None else "unknown",
            "observed_at": observed_at,
            "how": "The requested region.",
        },
        "size": size
        | {
            "source": "recorded" if size else "unknown",
            "observed_at": observed_at,
            "how": "The requested allocation.",
        },
        "creations": {
            "count": None,
            "source": "unknown",
            "observed_at": observed_at,
            "how": "No provider creation count.",
        },
        "intervals": intervals,
    }
    if requested.get("class") is not None:
        base["class"] = {
            "name": requested["class"],
            "source": "recorded",
            "observed_at": observed_at,
            "how": "The class the sandbox was created in.",
        }
    return base


def record_reason(evidence: Document, billing: Document, as_of: str) -> str:
    """Explain unavailable provider evidence inside or after its retry window."""
    window = billing.get("revisit")
    ended = revisit_end(evidence)
    now = parse_datetime(as_of)
    if window and ended is not None and now is not None:
        if now > ended + timedelta(seconds=window["until_s"]):
            return (
                f"{billing['name']}'s provider record was unavailable "
                "before the revisit window closed."
            )
    return f"Waiting for {billing['name']}'s per-sandbox provider record."


def _provider_timeline(
    evidence: Document, observed_at: str
) -> tuple[TimeValue, TimeValue, list[JsonObject]]:
    points = sorted(
        (
            (at, item)
            for item in evidence["provider_times"]
            if item["at"].get("source") == "provider"
            and item["kind"] in (*STARTS, *ENDS)
            and (at := parse_datetime(item["at"].get("value"))) is not None
        ),
        key=lambda pair: pair[0],
    )
    missing = TimeValue(None, "unknown", "Waiting for the provider's lifecycle record.")
    start, end = missing, missing
    intervals: list[JsonObject] = []
    previous: tuple[datetime, str] | None = None
    complete = bool(points) and points[0][1]["kind"] in STARTS
    for at, item in points:
        assert at is not None
        kind = item["kind"]
        if start.value is None and kind in STARTS:
            start = TimeValue(at, "provider", f"The provider's own time: {item['field']}.")
        if previous is not None:
            since, state = previous
            intervals.append(
                {
                    "state": state,
                    "seconds": (at - since).total_seconds(),
                    "source": "provider",
                    "observed_at": observed_at,
                    "how": "Elapsed time between provider lifecycle event timestamps.",
                }
            )
        if kind in STARTS:
            previous = (at, "running")
            end = missing
        else:
            end = TimeValue(at, "provider", f"The provider's own time: {item['field']}.")
            previous = (at, kind) if kind in ("paused", "stopped") else None
    return start, end, intervals if complete and end.value is not None else []


def call_returns(evidence: Document, name: str) -> list[object]:
    return [
        call["returned_at"].get("value")
        for call in evidence["calls"]
        if call["name"] == name
        and call["outcome"] == "returned"
        and isinstance(call.get("returned_at"), Mapping)
    ]


def sandbox_start(evidence: Document, usage: BillableUsage) -> TimeValue:
    """When the sandbox started: a provider lifecycle time, else the create call's return.

    Never a billing interval's bound.
    """
    start = usage.get("sandbox_start", usage["times"]["start"])
    if start.value is not None:
        return start
    returned = [
        parse_time(value) for value in call_returns(evidence, "create") if isinstance(value, str)
    ]
    if returned:
        return TimeValue(min(returned), "recorded", "When the provider's create call returned.")
    return start


def sandbox_end(evidence: Document, usage: BillableUsage) -> TimeValue:
    """When the sandbox ended: a provider lifecycle time, else the destroy return.

    Never a billing interval's bound; that is the bill row's own field, and a billing hour ends
    after the sandbox does.
    """
    end = usage.get("sandbox_end", usage["times"]["end"])
    if end.value is not None:
        return end
    returned = [
        parse_time(value) for value in call_returns(evidence, "destroy") if isinstance(value, str)
    ]
    if returned:
        return TimeValue(max(returned), "recorded", "When the provider's destroy call returned.")
    return end


def covers_sandbox(evidence: Document, result: BillableUsage, periods: Sequence[Document]) -> bool:
    """Whether a provider's cost periods leave out none of the sandbox's life.

    A figure that leaves part of the sandbox's life out would be a wrong total labelled as the
    provider's, so a rule reports its periods' cost only when this holds; otherwise the cost
    stays unknown until a later read brings the rest. The first period starts within
    `COVERAGE_EDGE_S` of the sandbox's start, the last ends within it of the sandbox's end, and
    no gap between periods is longer than it. A period without both of its times cannot show
    coverage. Periods are held back only when the sandbox's own times show they leave something
    out: with no known start or end there is nothing to compare them with, and a report that
    prices itself stays reported.

    The sandbox's times are its own (`sandbox_start`, `sandbox_end`), never a period's.
    """
    start, end = sandbox_start(evidence, result).value, sandbox_end(evidence, result).value
    if start is None or end is None:
        return True
    edge = timedelta(seconds=COVERAGE_EDGE_S)
    ordered: list[tuple[datetime, datetime]] = []
    for period in periods:
        begun = parse_datetime(period.get("interval_start"))
        stopped = parse_datetime(period.get("interval_end"))
        if begun is None or stopped is None:
            return False
        ordered.append((begun, stopped))
    ordered.sort()
    if not ordered or ordered[0][0] > start + edge:
        return False
    reached = ordered[0][1]
    for begun, stopped in ordered[1:]:
        if begun > reached + edge:
            return False
        reached = max(reached, stopped)
    return reached >= end - edge


def reported_periods(result: BillableUsage, readings: Sequence[Document]) -> None:
    """Retain the provider's cost-period times for rate identity and record revisits.

    Only `times` takes the period. The sandbox's own times stay in `sandbox_start`,
    `sandbox_end` and the usage record's `started`: a billing period's bounds are not when the
    sandbox ran.
    """
    for side, field, choose in (("start", "interval_start", min), ("end", "interval_end", max)):
        found = [at for row in readings if (at := parse_datetime(row.get(field))) is not None]
        if not found:
            continue
        result.setdefault(f"sandbox_{side}", result["times"][side])  # type: ignore[misc]
        result["times"][side] = TimeValue(
            choose(found), "provider", f"Provider cost report {field}."
        )


def waiting_for_record(
    evidence: Document, billing: Document, *, as_of: str | None = None
) -> BillableUsage:
    """Usage from lifecycle times, held as unknown until the provider's own record is read."""
    result = default_billable(evidence, as_of=as_of)
    observed_at = result["low"]["started"]["observed_at"]
    return unavailable(result, record_reason(evidence, billing, observed_at))


def latest_record(evidence: Document, source: str) -> Document | None:
    """The most recently read provider record from `source`, if any."""
    records = [record for record in evidence["provider_records"] if record["source"] == source]
    return max(records, key=lambda record: record["read_at"]) if records else None


def read_core_report(evidence: Document, kind: str) -> tuple[JsonObject, str] | None:
    """The latest Core report of `kind`, and when it was read."""
    report = core_report(evidence, kind)
    record = latest_record(evidence, f"core.{kind}")
    return None if report is None or record is None else (report, record["read_at"])


def provider_record_size(
    evidence: Document, billing: Document, version: Document | None
) -> JsonObject | None:
    """The allocated size the provider's own record names, resolved to published dimensions.

    Where the billing declaration names a record field carrying the provider's size name, the
    newest read of that field resolves the allocated bundle: the price version's per-size
    machine rate of the same name carries its published cpu, memory and disk. A sandbox created
    by minimums records no exact requested size; what the provider allocated is what the price
    version bills. A field never read, or a name no rate covers, leaves the size unknown — it
    is never estimated.
    """
    declared = billing.get("allocated_size")
    field = declared.get("record_field") if isinstance(declared, Mapping) else None
    if not isinstance(field, str) or not field or version is None:
        return None
    requested = evidence.get("requested")
    requested_class = requested.get("class") if isinstance(requested, Mapping) else None
    price_class = find_class(version, requested_class if isinstance(requested_class, str) else None)
    machine = (price_class or {}).get("rates", {}).get("machine")
    if not isinstance(machine, Mapping):
        return None
    records = sorted(
        evidence.get("provider_records") or (),
        key=lambda record: record.get("read_at") or "",
        reverse=True,
    )
    return next(
        (
            size
            for record in records
            if (size := _record_named_size(machine, field, record)) is not None
        ),
        None,
    )


def _record_named_size(machine: Document, field: str, record: Document) -> JsonObject | None:
    """The size doc one provider record resolves, when its named bundle is priced."""
    body = record.get("body")
    name = body.get(field) if isinstance(body, Mapping) else None
    bundle = machine.get(name) if isinstance(name, str) else None
    if not isinstance(bundle, Mapping):
        return None
    size: JsonObject = {
        key: amount
        for key, amount in (
            ("cpu", _bundle_dim(bundle.get("cpu"), 1)),
            ("memory_mib", _bundle_dim(bundle.get("memory_gib"), MIB_PER_GIB)),
            ("disk_mib", _bundle_dim(bundle.get("disk_gib"), MIB_PER_GIB)),
        )
        if amount is not None
    }
    if not size:
        return None
    return size | {
        "source": "provider",
        "observed_at": record["read_at"],
        "how": f"The provider's sandbox record named the allocated size {name}.",
    }


def _bundle_dim(value: object, factor: object) -> int | float | None:
    """A published bundle dimension in the usage size's unit; never a guessed number."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        amount = Decimal(str(value)) * Decimal(str(factor))
    except (ArithmeticError, ValueError):
        return None
    return int(amount) if amount == amount.to_integral_value() else float(amount)


def read_before_end(evidence: Document, record: Document) -> str | None:
    """Whether `record` was read before the sandbox ended, for a provider that deletes it then.

    A provider whose per-sandbox record vanishes with the sandbox has no final figure to read
    afterwards: the last read taken before the delete is all there is. The sandbox is known to
    have ended when a destroy call returned or Cloud noticed it gone, and the read was taken no
    later than that. This only places a read in time; it never builds a figure. It returns the
    read's own time, or None. A provider's rule decides whether a read that was still running
    at that point may stand as the cost, and labels it with that time (`report_cost(...,
    taken_at=...)`).
    """
    ended = [
        call["returned_at"].get("value")
        for call in evidence["calls"]
        if call["name"] == "destroy"
        and call["outcome"] == "returned"
        and isinstance(call.get("returned_at"), Mapping)
    ]
    gone = evidence.get("noticed_gone")
    ended.append(gone.get("value") if isinstance(gone, Mapping) else None)
    times = [at for value in ended if isinstance(value, str) and (at := parse_time(value))]
    read = parse_time(record["read_at"])
    return record["read_at"] if times and read <= max(times) else None


def report_cost(
    result: BillableUsage,
    usd: str,
    how: str,
    periods: Sequence[Document] = (),
    *,
    taken_at: str | None = None,
) -> BillableUsage:
    """Keep the provider's own cost of the sandbox, and the cost periods it covers when known.

    An interval still without billed seconds is then not waiting for a record: the provider
    reports this sandbox's cost, not its billed seconds. `taken_at` is the time of the read when
    the figure is the last one taken before the provider deleted its record: it may fall short
    of the sandbox's final usage and is never raised or replaced by an estimate.
    """
    if periods:
        reported_periods(result, periods)
    reported = {"usd": usd, "source": "provider", "how": how}
    if taken_at is not None:
        reported["taken_at"] = taken_at
    result["reported"] = reported
    for usage in (result["low"], result["high"]):
        for interval in usage["intervals"]:
            if interval["seconds"] is None:
                interval["how"] = REPORTED_WITHOUT_SECONDS
    return result


def stored_rates_match(
    provider: str,
    started: str | None,
    reported: Document | None,
    fields: Mapping[str, str],
    versions: Sequence[Document] | None = None,
) -> bool | None:
    """Whether `reported` rates equal the provider's stored list rates effective at `started`.

    `fields` maps each stored-rate resource to the provider's micro-USD field name. `versions`
    is the price-version pool in effect, defaulted to the bundled pool. Returns
    None when no stored version or no reported rates exist to compare.
    """
    pool = None if versions is None else [dict(item) for item in versions]
    version = price_version(provider, started, pool)
    if version is None or not isinstance(reported, dict):
        return None
    stored = next(item for item in version["classes"] if item.get("default"))["rates"]
    return not any(
        not isinstance(reported.get(field), int)
        or isinstance(reported[field], bool)
        or Decimal(reported[field]) != Decimal(stored[resource]["usd"]) * 1_000_000
        for resource, field in fields.items()
    )
