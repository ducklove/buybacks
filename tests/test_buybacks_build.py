from scripts.buybacks.build_buybacks_dataset import (
    companies_from_disclosures,
    dedupe_companies,
    filter_json_dataset_to_supported_markets,
    filter_live_dataset_to_supported_markets,
    parse_holding_stock_codes,
    parse_stock_codes,
    select_holding_companies,
)
from scripts.buybacks.models import Company, TreasuryHoldingSnapshot


def test_parse_stock_codes_all_uses_disclosure_only_mode():
    assert parse_stock_codes("ALL") is None
    assert parse_stock_codes("005930, 035420") == {"005930", "035420"}


def test_parse_holding_stock_codes_supports_all_events_and_explicit_codes():
    assert parse_holding_stock_codes("ALL") is None
    assert parse_holding_stock_codes("EVENTS") == "EVENTS"
    assert parse_holding_stock_codes("005930, 006800") == {"005930", "006800"}


def test_companies_from_disclosures_uses_list_rows_without_corp_master():
    companies = companies_from_disclosures(
        [
            {
                "corp_code": "00126380",
                "corp_name": "Samsung Electronics",
                "stock_code": "005930",
                "corp_cls": "Y",
                "rcept_dt": "20260620",
            },
            {
                "corp_code": "00126380",
                "corp_name": "Samsung Electronics",
                "stock_code": "005930",
                "corp_cls": "Y",
                "rcept_dt": "20260621",
            },
            {
                "corp_code": "bad",
                "corp_name": "Unlisted",
                "stock_code": "",
                "corp_cls": "E",
                "rcept_dt": "20260621",
            },
            {
                "corp_code": "00999999",
                "corp_name": "Konex Company",
                "stock_code": "123456",
                "corp_cls": "N",
                "rcept_dt": "20260621",
            },
        ]
    )

    assert len(companies) == 1
    assert companies[0].corp_code == "00126380"
    assert companies[0].stock_code == "005930"
    assert companies[0].market == "KOSPI"
    assert companies[0].last_updated == "2026-06-20"


def test_disclosure_only_candidates_keep_recent_order_before_truncation():
    companies = companies_from_disclosures(
        [
            {
                "corp_code": "00111722",
                "corp_name": "Mirae Asset Securities",
                "stock_code": "006800",
                "corp_cls": "Y",
                "rcept_dt": "20260617",
            },
            {
                "corp_code": "00620715",
                "corp_name": "Narae Nanotech",
                "stock_code": "137080",
                "corp_cls": "K",
                "rcept_dt": "20260616",
            },
        ]
    )

    assert [company.stock_code for company in companies] == ["006800", "137080"]


def test_dedupe_companies_can_preserve_source_order():
    companies = [
        Company("00111722", "006800", "Mirae Asset Securities", "KOSPI", None, "2026-06-17"),
        Company("00620715", "137080", "Narae Nanotech", "KOSDAQ", None, "2026-06-16"),
    ]

    assert [company.stock_code for company in dedupe_companies(companies, sort_by_name=False)] == [
        "006800",
        "137080",
    ]


def test_select_holding_companies_uses_full_master_for_all_scope():
    event_companies = [
        Company("00111722", "006800", "Mirae Asset Securities", "KOSPI", None, "2026-06-17")
    ]
    all_companies = [
        *event_companies,
        Company("00126380", "005930", "Samsung Electronics", "KOSPI", None, "2026-06-20"),
    ]

    selected = select_holding_companies(
        None,
        all_companies,
        event_companies,
        {company.stock_code: company for company in all_companies},
    )

    assert [company.stock_code for company in selected] == ["006800", "005930"]


def test_select_holding_companies_can_limit_to_event_scope():
    event_companies = [
        Company("00111722", "006800", "Mirae Asset Securities", "KOSPI", None, "2026-06-17")
    ]
    all_companies = [
        *event_companies,
        Company("00126380", "005930", "Samsung Electronics", "KOSPI", None, "2026-06-20"),
    ]

    selected = select_holding_companies(
        "EVENTS",
        all_companies,
        event_companies,
        {company.stock_code: company for company in all_companies},
    )

    assert selected == event_companies


def holding(stock_code: str) -> TreasuryHoldingSnapshot:
    return TreasuryHoldingSnapshot(
        corp_code="00126380",
        stock_code=stock_code,
        corp_name="Company",
        as_of_date="2025-12-31",
        report_year=2025,
        report_code="11011",
        stock_kind="common",
        beginning_qty=None,
        acquired_qty=None,
        disposed_qty=None,
        retired_qty=None,
        ending_qty=10,
        issued_shares=100,
        treasury_ratio=0.1,
        floating_shares=90,
        source_rcept_no=None,
    )


def test_filter_live_dataset_keeps_supported_markets_with_data_only():
    companies = [
        Company("00126380", "005930", "Samsung Electronics", "KOSPI", None, "2026-06-20"),
        Company("00620715", "137080", "Narae Nanotech", "KOSDAQ", None, "2026-06-16"),
        Company("00999999", "123456", "Konex Company", "KONEX", None, "2026-06-16"),
        Company("00888888", "999999", "No Data", "KOSPI", None, "2026-06-16"),
    ]

    filtered_companies, filtered_events, filtered_holdings = filter_live_dataset_to_supported_markets(
        companies,
        [],
        [holding("005930"), holding("137080"), holding("123456")],
    )

    assert filtered_events == []
    assert [company.stock_code for company in filtered_companies] == ["005930", "137080"]
    assert [snapshot.stock_code for snapshot in filtered_holdings] == ["005930", "137080"]


def test_filter_json_dataset_removes_unsupported_markets_and_orphan_reactions():
    companies = [
        {"stock_code": "005930", "market": "KOSPI"},
        {"stock_code": "123456", "market": "OTHER"},
    ]
    events = [
        {"event_id": "keep", "stock_code": "005930"},
        {"event_id": "drop", "stock_code": "123456"},
    ]
    holdings = [
        {"stock_code": "005930"},
        {"stock_code": "123456"},
    ]
    reactions = [
        {"event_id": "keep"},
        {"event_id": "drop"},
    ]

    filtered = filter_json_dataset_to_supported_markets(companies, events, holdings, reactions)

    assert filtered == (
        [{"stock_code": "005930", "market": "KOSPI"}],
        [{"event_id": "keep", "stock_code": "005930"}],
        [{"stock_code": "005930"}],
        [{"event_id": "keep"}],
    )
