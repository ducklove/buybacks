import json
import re
from pathlib import Path

import pytest

from scripts.buybacks import vc_publish
from scripts.buybacks.publish_summary import (
    build_summary_data,
    build_summary_envelope,
    publish_summary,
)

ROOT = Path(__file__).resolve().parents[1]
CODE = re.compile(r"^[0-9A-Z]{6}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STATUS = {"generated_at": "2026-09-27T23:34:19.538232+00:00"}


def snapshot(code, as_of, ratio, *, kind="보통주", name=None, report_code="11011", ending=None, issued=None):
    return {
        "corp_code": "0",
        "stock_code": code,
        "corp_name": name or f"회사{code}",
        "as_of_date": as_of,
        "report_year": int(as_of[:4]),
        "report_code": report_code,
        "stock_kind": kind,
        "ending_qty": ending,
        "issued_shares": issued,
        "treasury_ratio": ratio,
        "floating_shares": None,
    }


def assert_matches_hub_schema(data: dict) -> None:
    """Required keys and shapes of value-invest config/schemas/summary/buybacks.schema.json."""
    assert set(["asOf", "count", "top", "ratios", "ratioAsOf"]) <= set(data)
    assert data["asOf"] is None or DATE.match(data["asOf"])
    assert isinstance(data["count"], int) and data["count"] >= 0
    assert isinstance(data["top"], list) and len(data["top"]) <= 20
    for item in data["top"]:
        assert {"code", "name", "asOf", "treasuryRatioPct"} <= set(item)
        assert CODE.match(item["code"]) and item["name"]
        assert item["asOf"] is None or DATE.match(item["asOf"])
        assert isinstance(item["treasuryRatioPct"], (int, float)) and item["treasuryRatioPct"] >= 0
        for key in ("endingQty", "issuedShares"):
            assert item.get(key) is None or isinstance(item[key], int)
    assert all(CODE.match(code) and value >= 0 for code, value in data["ratios"].items())
    assert all(CODE.match(code) and DATE.match(value) for code, value in data["ratioAsOf"].items())
    assert data["count"] == len(data["ratios"])


def test_build_summary_keeps_latest_common_snapshot_per_code():
    holdings = [
        snapshot("005930", "2024-12-31", 0.02),
        snapshot("005930", "2025-12-31", 0.0155, ending=1000.0, issued=64519.0),
        snapshot("005935", "2025-12-31", 0.5, kind="우선주"),  # preferred rows never enter ratios
        snapshot("001720", "2025-03-31", 0.53102, name="신영증권"),
        snapshot("000660", "2025-12-31", None),  # no ratio -> skipped
    ]

    data = build_summary_data(holdings)

    assert data["asOf"] == "2025-12-31"
    assert data["count"] == 2
    assert data["ratios"] == {"001720": 53.1, "005930": 1.55}
    # Only codes whose snapshot date differs from data.asOf are listed.
    assert data["ratioAsOf"] == {"001720": "2025-03-31"}
    assert [item["code"] for item in data["top"]] == ["001720", "005930"]
    top = data["top"][1]
    assert top == {
        "code": "005930",
        "name": "회사005930",
        "asOf": "2025-12-31",
        "stockKind": "보통주",
        "treasuryRatioPct": 1.55,
        "endingQty": 1000,
        "issuedShares": 64519,
    }
    assert_matches_hub_schema(data)


def test_same_date_tie_prefers_more_complete_then_higher_report_code():
    holdings = [
        snapshot("005930", "2025-12-31", 0.01, report_code="11011"),
        snapshot("005930", "2025-12-31", 0.03, report_code="11014", ending=3, issued=100),
    ]
    assert build_summary_data(holdings)["ratios"] == {"005930": 3.0}


def test_envelope_validates_and_uses_dataset_scan_date_not_run_time():
    envelope = build_summary_envelope([snapshot("005930", "2025-12-31", 0.0155)], STATUS)

    vc_publish.validate_envelope(envelope)
    assert envelope["tool"] == "buybacks"
    assert envelope["kind"] == "summary"
    # data_status.generated_at 2026-09-27T23:34Z is 2026-09-28 08:34 KST.
    assert envelope["asOf"] == "2026-09-28"
    assert envelope["generatedAt"] == "2026-09-28T08:34:19+09:00"
    assert envelope["contentHash"] == vc_publish.content_hash(envelope["data"])


def test_envelope_rejects_missing_scan_time():
    with pytest.raises(vc_publish.EnvelopeError):
        build_summary_envelope([], {})


def write_dataset(data_dir: Path, holdings: list[dict], status: dict) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "holding_snapshots.json").write_text(json.dumps(holdings), encoding="utf-8")
    (data_dir / "data_status.json").write_text(json.dumps(status), encoding="utf-8")


def test_publish_writes_once_and_skips_unchanged_content(tmp_path):
    data_dir, out_dir = tmp_path / "data", tmp_path / "public"
    holdings = [snapshot("005930", "2025-12-31", 0.0155)]
    write_dataset(data_dir, holdings, STATUS)

    assert publish_summary(data_dir, out_dir) is True
    summary_bytes = (out_dir / "summary.json").read_bytes()
    version_bytes = (out_dir / "version.json").read_bytes()
    assert summary_bytes.endswith(b"\n") and summary_bytes.count(b"\n") == 1
    version = json.loads(version_bytes)
    assert version["files"] == {"summary.json": json.loads(summary_bytes)["contentHash"]}

    # Same data re-published: nothing is rewritten (no git diff, no deploy).
    assert publish_summary(data_dir, out_dir) is False
    assert (out_dir / "summary.json").read_bytes() == summary_bytes
    assert (out_dir / "version.json").read_bytes() == version_bytes

    # A changed ratio rewrites both files.
    write_dataset(data_dir, [snapshot("005930", "2025-12-31", 0.02)], STATUS)
    assert publish_summary(data_dir, out_dir) is True
    assert json.loads((out_dir / "summary.json").read_text())["data"]["ratios"] == {"005930": 2.0}
    assert (out_dir / "version.json").read_bytes() != version_bytes


def test_committed_summary_is_a_valid_envelope():
    envelope = json.loads((ROOT / "public" / "summary.json").read_text(encoding="utf-8"))
    vc_publish.validate_envelope(envelope)
    assert envelope["tool"] == "buybacks"
    assert_matches_hub_schema(envelope["data"])
    assert len((ROOT / "public" / "summary.json").read_bytes()) < 64 * 1024
    version = json.loads((ROOT / "public" / "version.json").read_text(encoding="utf-8"))
    assert version["tool"] == "buybacks"
    assert version["files"]["summary.json"] == envelope["contentHash"]
