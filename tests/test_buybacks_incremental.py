import argparse
import json

import scripts.buybacks.build_buybacks_dataset as build_module
from scripts.buybacks.build_buybacks_dataset import (
    build_incremental_dataset,
    merge_holdings,
    select_incremental_holding_companies,
    write_json,
)
from scripts.buybacks.fetch_krx_prices import missing_reaction
from scripts.buybacks.models import (
    BuybackEvent,
    BuybackExecution,
    Company,
    DividendRecord,
    TreasuryHoldingSnapshot,
    to_jsonable,
)


def company(corp_code: str, stock_code: str, name: str) -> Company:
    return Company(corp_code, stock_code, name, "KOSPI", None, "2026-06-30")


def event(event_id: str, stock_code: str, corp_code: str, disclosure_date: str, rcept_no: str) -> BuybackEvent:
    return BuybackEvent(
        event_id=event_id,
        corp_code=corp_code,
        stock_code=stock_code,
        corp_name="Company",
        event_type="direct_acquisition",
        disclosure_date=disclosure_date,
        decision_date=disclosure_date,
        period_start=None,
        period_end=None,
        planned_shares_common=1000,
        planned_shares_other=None,
        planned_amount_krw=None,
        planned_amount_common_krw=None,
        planned_amount_other_krw=None,
        planned_share_ratio_common=None,
        planned_share_ratio_other=None,
        actual_shares=None,
        actual_amount_krw=None,
        method=None,
        purpose=None,
        broker=None,
        holding_before_common=None,
        holding_before_ratio_common=None,
        source="DART",
        rcept_no=rcept_no,
        source_url=None,
        raw_report_name=None,
    )


def execution(
    rcept_no: str,
    stock_code: str,
    corp_code: str,
    disclosure_date: str,
    origin_report_date: str | None,
) -> BuybackExecution:
    return BuybackExecution(
        execution_id=f"dart-{rcept_no}-acquisition_result",
        corp_code=corp_code,
        stock_code=stock_code,
        corp_name="Company",
        execution_type="acquisition_result",
        disclosure_date=disclosure_date,
        origin_report_date=origin_report_date,
        period_start=None,
        period_end=None,
        ordered_shares=None,
        actual_shares=1000,
        actual_amount_krw=None,
        avg_price_krw=None,
        planned_amount_krw=None,
        planned_shares=None,
        shortfall=None,
        shortfall_reason=None,
        holding_after_qty=None,
        holding_after_ratio=None,
        trust_contract_amount_krw=None,
        trust_progress_ratio=None,
        as_of_date=None,
        linked_event_id=None,
        link_method="unlinked",
        source="DART",
        rcept_no=rcept_no,
        source_url=None,
        raw_report_name="자기주식취득결과보고서",
    )


def holding(stock_code: str, corp_code: str, ending_qty: int) -> TreasuryHoldingSnapshot:
    return TreasuryHoldingSnapshot(
        corp_code=corp_code,
        stock_code=stock_code,
        corp_name="Company",
        as_of_date="2025-12-31",
        report_year=2025,
        report_code="11011",
        stock_kind="보통주",
        beginning_qty=None,
        acquired_qty=None,
        disposed_qty=None,
        retired_qty=None,
        ending_qty=ending_qty,
        issued_shares=10_000,
        treasury_ratio=ending_qty / 10_000,
        floating_shares=10_000 - ending_qty,
        source_rcept_no=None,
    )


def dividend(stock_code: str, corp_code: str, dps: int, bsns_year: int = 2025) -> DividendRecord:
    return DividendRecord(
        corp_code=corp_code,
        stock_code=stock_code,
        corp_name="Company",
        bsns_year=bsns_year,
        report_code="11011",
        dps_common_krw=dps,
        cash_dividend_total_krw=dps * 10_000,
        payout_ratio=0.25,
        net_income_krw=None,
        rcept_no=None,
    )


def make_args(tmp_path, **overrides) -> argparse.Namespace:
    values = {
        "raw_dir": str(tmp_path / "raw"),
        "start": "",
        "end": "20260701",
        "years": "2025",
        "report_codes": "11011",
        "holding_source": "stock_totals",
        "holding_stock_codes": "ALL",
        "dividend_stock_codes": "EVENTS",
        "max_holding_companies": 0,
        "incremental_lookback_days": 7,
        "incremental_price_lookback_days": 75,
        "price_reaction_scope": "recent",
        "discovery_page_limit": 50,
        "price_source": "missing",
        "latest_price_lookback_days": 10,
        "listed_issue_source": "none",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def write_existing_dataset(output_dir) -> None:
    old_event = event("dart-old-direct_acquisition", "005930", "00126380", "2026-05-01", "20260501000001")
    write_json(output_dir / "companies.json", to_jsonable([company("00126380", "005930", "Samsung")]))
    write_json(output_dir / "events.json", to_jsonable([old_event]))
    write_json(output_dir / "holding_snapshots.json", to_jsonable([holding("005930", "00126380", 100)]))
    write_json(
        output_dir / "price_reactions.json",
        to_jsonable([missing_reaction(old_event.event_id, "005930", "2026-05-01")]),
    )
    write_json(output_dir / "latest_prices.json", [])
    write_json(
        output_dir / "data_status.json",
        {
            "generated_at": "2026-06-30T00:00:00+00:00",
            "price_source": "missing",
            "latest_price_source": "missing",
            "companies_count": 1,
            "events_count": 1,
            "holdings_count": 1,
            "price_reactions_count": 1,
            "latest_prices_count": 0,
            "warnings": [],
        },
    )


def patch_incremental_collectors(monkeypatch, corp_code_calls, holding_scan_scopes, dividend_scan_scopes=None):
    naver = company("00266961", "035420", "NAVER")
    new_event = event("dart-new-direct_acquisition", "035420", "00266961", "2026-06-30", "20260630000001")
    master = [
        company("00126380", "005930", "Samsung"),
        company("00266961", "035420", "NAVER"),
        company("00164779", "000660", "SK hynix"),
    ]

    def fake_fetch_disclosures(api_key, bgn_de, end_de, raw_dir=None, page_limit=20, disclosure_types=None):
        return (
            [
                {
                    "corp_code": "00266961",
                    "corp_name": "NAVER",
                    "stock_code": "035420",
                    "corp_cls": "Y",
                    "rcept_dt": "20260630",
                    "rcept_no": "20260630000001",
                    "report_nm": "주요사항보고서(자기주식취득결정)",
                }
            ],
            [],
        )

    def fake_collect_dataset(**kwargs):
        return [naver], [new_event], [], []

    def fake_fetch_corp_codes(api_key, output=None):
        corp_code_calls.append(api_key)
        return master

    def fake_collect_holdings(api_key, companies, years, raw_dir=None, report_codes=None, include_treasury_tables=True):
        scanned = list(companies)
        holding_scan_scopes.append([item.corp_code for item in scanned])
        return [holding(item.stock_code, item.corp_code, 120) for item in scanned], []

    def fake_collect_execution_reports(api_key, bgn_de, end_de, raw_dir=None, page_limit=20):
        return [], []

    def fake_collect_dividends(api_key, companies, years, raw_dir=None, report_codes=None):
        scanned = list(companies)
        if dividend_scan_scopes is not None:
            dividend_scan_scopes.append([item.corp_code for item in scanned])
        return [dividend(item.stock_code, item.corp_code, 500) for item in scanned], []

    monkeypatch.setattr(build_module, "fetch_buyback_disclosures", fake_fetch_disclosures)
    monkeypatch.setattr(build_module, "collect_dart_dataset", fake_collect_dataset)
    monkeypatch.setattr(build_module, "fetch_corp_codes", fake_fetch_corp_codes)
    monkeypatch.setattr(build_module, "collect_dart_holding_snapshots", fake_collect_holdings)
    monkeypatch.setattr(build_module, "collect_execution_reports", fake_collect_execution_reports)
    monkeypatch.setattr(build_module, "collect_dividend_records", fake_collect_dividends)


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_incremental_all_scope_scans_full_universe_and_keeps_merged_events(monkeypatch, tmp_path):
    output_dir = tmp_path / "out"
    write_existing_dataset(output_dir)
    corp_code_calls: list[str] = []
    holding_scan_scopes: list[list[str]] = []
    patch_incremental_collectors(monkeypatch, corp_code_calls, holding_scan_scopes)

    args = make_args(tmp_path, holding_stock_codes="ALL")
    status = build_incremental_dataset(args, "key", output_dir)

    # Events stay merge-based: old event survives, new event added.
    event_ids = {item["event_id"] for item in load(output_dir / "events.json")}
    assert event_ids == {"dart-old-direct_acquisition", "dart-new-direct_acquisition"}
    assert status["events_count"] == 2

    # Holding scan covered the full corp master, not just event companies.
    assert corp_code_calls == ["key"]
    assert holding_scan_scopes == [["00126380", "00266961", "00164779"]]

    holdings = {item["stock_code"]: item for item in load(output_dir / "holding_snapshots.json")}
    assert set(holdings) == {"005930", "035420", "000660"}
    # Refreshed snapshot replaced the stale row with the same dedupe key.
    assert holdings["005930"]["ending_qty"] == 120

    # Holding-only company from the all-market scan reaches companies.json.
    company_codes = {item["stock_code"] for item in load(output_dir / "companies.json")}
    assert company_codes == {"005930", "035420", "000660"}


def test_incremental_events_scope_keeps_event_company_behavior(monkeypatch, tmp_path):
    output_dir = tmp_path / "out"
    write_existing_dataset(output_dir)
    corp_code_calls: list[str] = []
    holding_scan_scopes: list[list[str]] = []
    patch_incremental_collectors(monkeypatch, corp_code_calls, holding_scan_scopes)

    args = make_args(tmp_path, holding_stock_codes="EVENTS")
    status = build_incremental_dataset(args, "key", output_dir)

    # EVENTS scope must not touch the corp master and scans event companies only.
    assert corp_code_calls == []
    assert holding_scan_scopes == [["00266961"]]

    event_ids = {item["event_id"] for item in load(output_dir / "events.json")}
    assert event_ids == {"dart-old-direct_acquisition", "dart-new-direct_acquisition"}
    assert status["events_count"] == 2

    holdings = {item["stock_code"]: item for item in load(output_dir / "holding_snapshots.json")}
    assert set(holdings) == {"005930", "035420"}
    # Existing snapshot outside the event scope is preserved untouched.
    assert holdings["005930"]["ending_qty"] == 100


def test_incremental_merges_and_relinks_executions(monkeypatch, tmp_path):
    output_dir = tmp_path / "out"
    write_existing_dataset(output_dir)
    # Existing execution referencing the old event through its origin date.
    write_json(
        output_dir / "executions.json",
        to_jsonable([execution("20260610000900", "005930", "00126380", "2026-06-10", "2026-05-01")]),
    )
    corp_code_calls: list[str] = []
    holding_scan_scopes: list[list[str]] = []
    patch_incremental_collectors(monkeypatch, corp_code_calls, holding_scan_scopes)

    new_execution = execution("20260701000900", "035420", "00266961", "2026-07-01", "2026-06-30")

    def fake_collect_execution_reports(api_key, bgn_de, end_de, raw_dir=None, page_limit=20):
        return [new_execution], ["execution warning"]

    monkeypatch.setattr(build_module, "collect_execution_reports", fake_collect_execution_reports)

    args = make_args(tmp_path, holding_stock_codes="EVENTS")
    status = build_incremental_dataset(args, "key", output_dir)

    stored = {item["rcept_no"]: item for item in load(output_dir / "executions.json")}
    assert set(stored) == {"20260610000900", "20260701000900"}
    # Both executions are (re)linked against the merged events on every build.
    assert stored["20260610000900"]["linked_event_id"] == "dart-old-direct_acquisition"
    assert stored["20260610000900"]["link_method"] == "report_date"
    assert stored["20260701000900"]["linked_event_id"] == "dart-new-direct_acquisition"
    assert status["executions_count"] == 2
    assert "execution warning" in status["warnings"]
    assert any("0 unlinked" in warning for warning in status["warnings"])


def test_incremental_without_existing_executions_file_still_writes_dataset(monkeypatch, tmp_path):
    output_dir = tmp_path / "out"
    write_existing_dataset(output_dir)
    corp_code_calls: list[str] = []
    holding_scan_scopes: list[list[str]] = []
    patch_incremental_collectors(monkeypatch, corp_code_calls, holding_scan_scopes)

    args = make_args(tmp_path, holding_stock_codes="EVENTS")
    status = build_incremental_dataset(args, "key", output_dir)

    assert status["executions_count"] == 0
    assert load(output_dir / "executions.json") == []


def test_incremental_preserves_series_prunes_dangling_and_writes_car_curves(monkeypatch, tmp_path):
    output_dir = tmp_path / "out"
    write_existing_dataset(output_dir)
    write_json(
        output_dir / "reaction_series.json",
        [
            {
                "event_id": "dart-old-direct_acquisition",
                "stock_code": "005930",
                "event_date": "2026-05-01",
                "t0_date": "2026-05-02",
                "daily_return": [0.012, -0.003],
                "daily_abnormal": [0.01, -0.004],
                "data_quality": "partial",
            },
            {
                "event_id": "dart-gone-direct_acquisition",
                "stock_code": "005930",
                "event_date": "2026-04-01",
                "t0_date": "2026-04-02",
                "daily_return": [0.02],
                "daily_abnormal": [0.02],
                "data_quality": "partial",
            },
        ],
    )
    corp_code_calls: list[str] = []
    holding_scan_scopes: list[list[str]] = []
    patch_incremental_collectors(monkeypatch, corp_code_calls, holding_scan_scopes)

    args = make_args(tmp_path, holding_stock_codes="EVENTS")
    status = build_incremental_dataset(args, "key", output_dir)

    # The old event's series survives even though its reaction was refreshed
    # to missing (price_source missing produces no replacement series), while
    # the series of the event that no longer exists is pruned.
    series = load(output_dir / "reaction_series.json")
    assert [item["event_id"] for item in series] == ["dart-old-direct_acquisition"]
    assert series[0]["daily_return"] == [0.012, -0.003]

    # CAR curves are re-aggregated every build: one series stays below
    # min_events, so the file exists with an empty group list.
    car = load(output_dir / "car_curves.json")
    assert car["window"] == 60
    assert car["min_events"] == 5
    assert car["groups"] == []

    assert status["reaction_series_count"] == 1
    assert status["car_groups_count"] == 0
    assert any("Reaction series missing for 1 of 2 events" in warning for warning in status["warnings"])


def test_incremental_without_existing_series_file_writes_empty_optional_files(monkeypatch, tmp_path):
    output_dir = tmp_path / "out"
    write_existing_dataset(output_dir)
    corp_code_calls: list[str] = []
    holding_scan_scopes: list[list[str]] = []
    patch_incremental_collectors(monkeypatch, corp_code_calls, holding_scan_scopes)

    args = make_args(tmp_path, holding_stock_codes="EVENTS")
    status = build_incremental_dataset(args, "key", output_dir)

    assert load(output_dir / "reaction_series.json") == []
    assert load(output_dir / "car_curves.json")["groups"] == []
    assert status["reaction_series_count"] == 0
    assert status["car_groups_count"] == 0


def test_merge_holdings_prefers_refreshed_rows_for_identical_keys():
    existing = [holding("005930", "00126380", 100)]
    refreshed = [holding("005930", "00126380", 120)]

    merged = merge_holdings(existing, refreshed)

    assert len(merged) == 1
    assert merged[0].ending_qty == 120


def test_incremental_merges_dividends_and_preserves_existing_years(monkeypatch, tmp_path):
    output_dir = tmp_path / "out"
    write_existing_dataset(output_dir)
    # Existing dividends: an old year for Samsung and a stale NAVER row that a
    # fresh scan must replace ((corp_code, bsns_year) key match).
    write_json(
        output_dir / "dividends.json",
        to_jsonable(
            [
                dividend("005930", "00126380", 1400, bsns_year=2024),
                dividend("035420", "00266961", 100, bsns_year=2025),
            ]
        ),
    )
    corp_code_calls: list[str] = []
    holding_scan_scopes: list[list[str]] = []
    dividend_scan_scopes: list[list[str]] = []
    patch_incremental_collectors(monkeypatch, corp_code_calls, holding_scan_scopes, dividend_scan_scopes)

    args = make_args(tmp_path, holding_stock_codes="EVENTS")
    status = build_incremental_dataset(args, "key", output_dir)

    # Default EVENTS scope scans only the event company (NAVER), no corp master.
    assert dividend_scan_scopes == [["00266961"]]

    stored = {(item["corp_code"], item["bsns_year"]): item for item in load(output_dir / "dividends.json")}
    assert set(stored) == {("00126380", 2024), ("00266961", 2025)}
    # Existing off-scope year is preserved untouched.
    assert stored[("00126380", 2024)]["dps_common_krw"] == 1400
    # Refreshed row replaced the stale row with the same key.
    assert stored[("00266961", 2025)]["dps_common_krw"] == 500
    assert status["dividends_count"] == 2
    assert any("dividend scan scope: 1 companies" in warning for warning in status["warnings"])


def test_incremental_all_dividend_scope_scans_corp_master(monkeypatch, tmp_path):
    output_dir = tmp_path / "out"
    write_existing_dataset(output_dir)
    corp_code_calls: list[str] = []
    holding_scan_scopes: list[list[str]] = []
    dividend_scan_scopes: list[list[str]] = []
    patch_incremental_collectors(monkeypatch, corp_code_calls, holding_scan_scopes, dividend_scan_scopes)

    args = make_args(tmp_path, holding_stock_codes="EVENTS", dividend_stock_codes="ALL")
    status = build_incremental_dataset(args, "key", output_dir)

    assert dividend_scan_scopes == [["00126380", "00266961", "00164779"]]
    assert status["dividends_count"] == 3


def test_incremental_without_existing_dividends_file_still_writes_dataset(monkeypatch, tmp_path):
    output_dir = tmp_path / "out"
    write_existing_dataset(output_dir)
    corp_code_calls: list[str] = []
    holding_scan_scopes: list[list[str]] = []
    patch_incremental_collectors(monkeypatch, corp_code_calls, holding_scan_scopes)

    def fake_collect_dividends(api_key, companies, years, raw_dir=None, report_codes=None):
        return [], []

    monkeypatch.setattr(build_module, "collect_dividend_records", fake_collect_dividends)

    args = make_args(tmp_path, holding_stock_codes="EVENTS")
    status = build_incremental_dataset(args, "key", output_dir)

    assert load(output_dir / "dividends.json") == []
    assert status["dividends_count"] == 0


def test_select_incremental_holding_companies_respects_max_limit(monkeypatch, tmp_path):
    master = [
        company("00126380", "005930", "Samsung"),
        company("00266961", "035420", "NAVER"),
        company("00164779", "000660", "SK hynix"),
    ]
    monkeypatch.setattr(build_module, "fetch_corp_codes", lambda api_key, output=None: master)
    args = make_args(tmp_path, holding_stock_codes="ALL", max_holding_companies=2)
    warnings: list[str] = []

    selected = select_incremental_holding_companies(args, "key", None, [], tmp_path / "raw", warnings)

    assert [item.corp_code for item in selected] == ["00126380", "00266961"]
    assert any("truncated" in warning for warning in warnings)
