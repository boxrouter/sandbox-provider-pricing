# SPDX-FileCopyrightText: BoxRouter, Inc.
# SPDX-License-Identifier: Apache-2.0
"""Rates reconciliation command tests."""

import json
from pathlib import Path
from typing import Any

from sandbox_provider_pricing.watch.cli import main


def test_reconcile_uses_price_version_at_each_period_start(tmp_path: Path, capsys: Any) -> None:
    provider_dir = tmp_path / "providers" / "example"
    prices = provider_dir / "prices"
    reconciliation = provider_dir / "evidence" / "reconciliations" / "2026-01"
    prices.mkdir(parents=True)
    reconciliation.mkdir(parents=True)
    (prices / "2026-01-01.yaml").write_text(
        """version: example@2026-01-01
provider: example
effective_from: '2026-01-01T00:00:00Z'
retrieved_at: '2026-01-01T00:00:00Z'
classes:
- name: default
  default: true
  rates:
    cpu:
      usd: '0.12'
      per: vcpu-hour
    memory:
      usd: '0.02'
      per: gb-hour
""",
        encoding="utf-8",
    )
    (prices / "2026-01-02.yaml").write_text(
        """version: example@2026-01-02
provider: example
effective_from: '2026-01-01T00:00:00Z'
retrieved_at: '2026-01-02T00:00:00Z'
classes:
- name: default
  default: true
  rates:
    cpu:
      usd: '0.12'
      per: vcpu-hour
    memory:
      usd: '0.02'
      per: gb-hour
""",
        encoding="utf-8",
    )
    rows = [
        {"period_start": "2026-01-01T00:00:00Z", "meter": "cpu", "quantity": 0.5, "cost_usd": 0.06},
        {
            "period_start": "2026-01-02T00:00:00Z",
            "meter": "memory",
            "quantity": 2,
            "cost_usd": 0.040000000005,
        },
        {"period_start": "2026-01-03T00:00:00Z", "meter": "cpu", "quantity": 1, "cost_usd": 0.11},
    ]
    bill = reconciliation / "bill.jsonl"
    bill.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    assert main(["reconcile", str(reconciliation)]) == 0
    assert capsys.readouterr().out == "rates check: cpu 1/2, memory 1/1 rows within 1e-11 USD\n"
    first = json.loads((reconciliation / "result.json").read_text(encoding="utf-8"))
    assert {check["price_version"] for check in first["checks"]} == {"example@2026-01-02"}

    (prices / "2026-02-01.yaml").write_text(
        """version: example@2026-02-01
provider: example
effective_from: '2026-02-01T00:00:00Z'
retrieved_at: '2026-02-01T00:00:00Z'
classes:
- name: default
  default: true
  rates:
    cpu:
      usd: '0.30'
      per: vcpu-hour
""",
        encoding="utf-8",
    )
    rows.append(
        {"period_start": "2026-02-01T00:00:00Z", "meter": "cpu", "quantity": 1, "cost_usd": 0.30}
    )
    bill.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    assert main(["reconcile", str(reconciliation)]) == 0
    assert capsys.readouterr().out == "rates check: cpu 2/3, memory 1/1 rows within 1e-11 USD\n"
    later = json.loads((reconciliation / "result.json").read_text(encoding="utf-8"))
    assert later["checks"][:3] == first["checks"]
    assert [check["price_version"] for check in later["checks"]] == [
        "example@2026-01-02",
        "example@2026-01-02",
        "example@2026-01-02",
        "example@2026-02-01",
    ]
