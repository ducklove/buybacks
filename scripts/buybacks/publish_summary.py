"""Publish the Value Compass hub summary (public/summary.json + public/version.json).

The value-invest hub used to download the whole holding_snapshots.json (~1.2 MB)
to read one treasury ratio per stock. This step reduces it to the envelope v1
``summary.json`` defined by the hub's data contract
(value-invest docs/ecosystem/data-contract.md §6.4,
config/schemas/summary/buybacks.schema.json). Vite copies ``public/`` to the
Pages root, so the files are served at https://ducklove.github.io/buybacks/summary.json.

Selection rule = value-invest ``external_tools._summarize_buybacks``: per stock and
stock kind keep the newest snapshot (date, then filled fields, then report_code),
then keep the common-stock rows that have a treasury_ratio.

The files are only rewritten when the content changes (vc_publish.write_if_changed),
so a re-run over the same dataset produces no git diff. Runs offline.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    from scripts.buybacks import vc_publish
else:
    from . import vc_publish

TOOL_ID = "buybacks"
TOP_N = 10
SOURCES = [{"id": "opendart", "name": "OpenDART", "url": "https://opendart.fss.or.kr/"}]
KST = timezone(timedelta(hours=9))
COMPLETENESS_FIELDS = ("treasury_ratio", "ending_qty", "issued_shares", "floating_shares")


def kind_key(row: dict) -> str:
    kind = str(row.get("stock_kind") or "").strip().replace(" ", "").lower()
    if "보통" in kind or "common" in kind:
        return "common"
    if "우선" in kind or "preferred" in kind:
        return f"preferred:{kind}"
    return kind or "unknown"


def completeness(row: dict) -> int:
    return sum(row.get(key) is not None for key in COMPLETENESS_FIELDS)


def is_newer(row: dict, current: dict) -> bool:
    row_date = str(row.get("as_of_date") or "")
    current_date = str(current.get("as_of_date") or "")
    if row_date != current_date:
        return row_date > current_date
    if completeness(row) != completeness(current):
        return completeness(row) > completeness(current)
    return str(row.get("report_code") or "") > str(current.get("report_code") or "")


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value == value and abs(value) != float("inf") else None


def _integer(value: object) -> int | None:
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def build_summary_data(holdings: list[dict], top_n: int = TOP_N) -> dict:
    latest: dict[tuple[str, str], dict] = {}
    for row in holdings or []:
        if not isinstance(row, dict):
            continue
        code = str(row.get("stock_code") or "").strip().upper()
        if not code:
            continue
        key = (code, kind_key(row))
        current = latest.get(key)
        if current is None or is_newer(row, current):
            latest[key] = row

    rows = []
    for (code, kind), row in latest.items():
        ratio = _number(row.get("treasury_ratio"))
        if kind != "common" or ratio is None or ratio < 0:
            continue
        rows.append(
            {
                "code": code,
                "name": str(row.get("corp_name") or "").strip() or code,
                "asOf": row.get("as_of_date") or None,
                "stockKind": row.get("stock_kind") or None,
                "treasuryRatioPct": round(ratio * 100, 4),
                "endingQty": _integer(row.get("ending_qty")),
                "issuedShares": _integer(row.get("issued_shares")),
            }
        )
    # Ratio descending; code breaks ties so the output is deterministic.
    rows.sort(key=lambda item: (-item["treasuryRatioPct"], item["code"]))
    dates = [item["asOf"] for item in rows if item["asOf"]]
    as_of = max(dates) if dates else None
    return {
        "asOf": as_of,
        "count": len(rows),
        "top": rows[:top_n],
        "ratios": {item["code"]: round(item["treasuryRatioPct"], 2) for item in sorted(rows, key=lambda r: r["code"])},
        "ratioAsOf": {
            item["code"]: item["asOf"]
            for item in sorted(rows, key=lambda r: r["code"])
            if item["asOf"] and item["asOf"] != as_of
        },
    }


def dataset_kst(status: dict) -> datetime | None:
    """data_status.generated_at (UTC) as a KST datetime: when the dataset was scanned."""
    raw = str(status.get("generated_at") or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(KST).replace(microsecond=0)


def build_summary_envelope(holdings: list[dict], status: dict) -> dict:
    """Envelope v1. asOf = KST date of the dataset scan (contract §6.4), never run time.

    generatedAt is the dataset build time too, so rebuilding from the same
    committed files yields byte-identical output.
    """
    scanned = dataset_kst(status)
    if scanned is None:
        raise vc_publish.EnvelopeError("data_status.generated_at is missing or invalid")
    return vc_publish.build_envelope(
        TOOL_ID,
        build_summary_data(holdings),
        as_of=scanned.date(),
        sources=SOURCES,
        generated_at=scanned,
    )


def publish_summary(data_dir: Path, out_dir: Path) -> bool:
    """Write out_dir/summary.json and out_dir/version.json when the content changed."""
    holdings = json.loads((data_dir / "holding_snapshots.json").read_text(encoding="utf-8"))
    status = json.loads((data_dir / "data_status.json").read_text(encoding="utf-8"))
    envelope = build_summary_envelope(holdings, status)
    changed = vc_publish.write_if_changed(out_dir / "summary.json", envelope)
    vc_publish.write_version(
        out_dir / "version.json",
        {"summary.json": envelope},
        generated_at=envelope["generatedAt"],
    )
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=Path("public/data/buybacks"))
    parser.add_argument("--out-dir", type=Path, default=Path("public"))
    args = parser.parse_args(argv)
    changed = publish_summary(args.data_dir, args.out_dir)
    print(f"summary.json {'updated' if changed else 'unchanged'} in {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
