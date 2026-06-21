from scripts.buybacks.build_buybacks_dataset import (
    companies_from_disclosures,
    dedupe_companies,
    filter_json_dataset_to_supported_markets,
    filter_live_dataset_to_supported_markets,
    incremental_start_yyyymmdd,
    merge_price_reactions,
    parse_holding_stock_codes,
    parse_stock_codes,
    select_holding_companies,
    select_price_reaction_events,
)
from scripts.buybacks.fetch_listed_issues import ListedIssue
from scripts.buybacks.models import BuybackEvent, Company, PriceReaction, TreasuryHoldingSnapshot


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


def holding(
    stock_code: str,
    stock_kind: str = "common",
    corp_code: str = "00126380",
    corp_name: str = "Company",
) -> TreasuryHoldingSnapshot:
    return TreasuryHoldingSnapshot(
        corp_code=corp_code,
        stock_code=stock_code,
        corp_name=corp_name,
        as_of_date="2025-12-31",
        report_year=2025,
        report_code="11011",
        stock_kind=stock_kind,
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


def event(
    event_id: str,
    disclosure_date: str,
    stock_code: str = "005930",
) -> BuybackEvent:
    return BuybackEvent(
        event_id=event_id,
        corp_code="00126380",
        stock_code=stock_code,
        corp_name="Company",
        event_type="direct_acquisition",
        disclosure_date=disclosure_date,
        decision_date=disclosure_date,
        period_start=None,
        period_end=None,
        planned_shares_common=None,
        planned_shares_other=None,
        planned_amount_krw=None,
        planned_amount_common_krw=None,
        planned_amount_other_krw=None,
        actual_shares=None,
        actual_amount_krw=None,
        method=None,
        purpose=None,
        broker=None,
        holding_before_common=None,
        holding_before_ratio_common=None,
        source="DART",
        rcept_no=None,
        source_url=None,
        raw_report_name=None,
    )


def reaction(event_id: str, event_date: str, quality: str = "partial") -> PriceReaction:
    return PriceReaction(
        event_id=event_id,
        stock_code="005930",
        event_date=event_date,
        close_t0=100,
        return_1d=0.01,
        return_5d=None,
        return_20d=None,
        return_60d=0.05 if quality == "complete" else None,
        max_drawdown_20d=None,
        max_drawdown_60d=None,
        market_return_5d=0.01 if quality == "complete" else None,
        abnormal_return_5d=0.02 if quality == "complete" else None,
        market_return_20d=None,
        abnormal_return_20d=None,
        market_return_60d=0.03 if quality == "complete" else None,
        abnormal_return_60d=0.04 if quality == "complete" else None,
        volume_change_20d=None,
        data_quality=quality,  # type: ignore[arg-type]
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
        [],
    )

    assert filtered_events == []
    assert [company.stock_code for company in filtered_companies] == ["005930", "137080"]
    assert [snapshot.stock_code for snapshot in filtered_holdings] == ["005930", "137080"]


def test_filter_live_dataset_maps_tradable_preferred_holding_to_listed_issue_code():
    companies = [
        Company("00111722", "006800", "Mirae Asset Securities", "KOSPI", None, "2026-06-17"),
    ]
    listed_issues = [
        ListedIssue("006800", "Mirae Asset Securities", "KOSPI", True),
        ListedIssue("00680K", "Mirae Asset Securities우", "KOSPI", True),
    ]

    filtered_companies, _, filtered_holdings = filter_live_dataset_to_supported_markets(
        companies,
        [],
        [
            holding("006800", "common", "00111722", "Mirae Asset Securities"),
            holding("006800", "preferred", "00111722", "Mirae Asset Securities"),
        ],
        listed_issues,
    )

    assert [company.stock_code for company in filtered_companies] == ["006800", "00680K"]
    assert [snapshot.stock_code for snapshot in filtered_holdings] == ["006800", "00680K"]
    assert filtered_holdings[1].corp_name == "Mirae Asset Securities우"


def test_filter_live_dataset_does_not_match_other_company_preferred_by_short_prefix():
    companies = [
        Company("00120000", "003550", "LG", "KOSPI", None, "2026-06-17"),
    ]
    listed_issues = [
        ListedIssue("003550", "LG", "KOSPI", True),
        ListedIssue("066575", "LG Electronics우", "KOSPI", True),
    ]

    _, _, filtered_holdings = filter_live_dataset_to_supported_markets(
        companies,
        [],
        [holding("003550", "preferred", "00120000", "LG")],
        listed_issues,
    )

    assert filtered_holdings == []


def test_filter_live_dataset_keeps_already_mapped_preferred_issue_code():
    companies = [
        Company("00111722", "006800", "Mirae Asset Securities", "KOSPI", None, "2026-06-17"),
        Company("00111722", "00680K", "Mirae Asset Securities우", "KOSPI", None, "2026-06-17"),
    ]
    listed_issues = [
        ListedIssue("006800", "Mirae Asset Securities", "KOSPI", True),
        ListedIssue("00680K", "Mirae Asset Securities우", "KOSPI", True),
    ]

    filtered_companies, _, filtered_holdings = filter_live_dataset_to_supported_markets(
        companies,
        [],
        [holding("00680K", "preferred", "00111722", "Mirae Asset Securities우")],
        listed_issues,
    )

    assert [company.stock_code for company in filtered_companies] == ["00680K"]
    assert [snapshot.stock_code for snapshot in filtered_holdings] == ["00680K"]


def test_incremental_start_uses_latest_existing_event_with_overlap():
    assert incremental_start_yyyymmdd(
        [event("old", "2026-06-10"), event("new", "2026-06-20")],
        "20260621",
        7,
    ) == "20260613"


def test_select_price_reaction_events_refreshes_new_missing_and_recent_partial_only():
    events = [
        event("new", "2026-06-21"),
        event("recent-partial", "2026-06-10"),
        event("recent-complete", "2026-06-09"),
        event("old-partial", "2026-01-01"),
    ]
    selected = select_price_reaction_events(
        events,
        [
            reaction("recent-partial", "2026-06-10", "partial"),
            reaction("recent-complete", "2026-06-09", "complete"),
            reaction("old-partial", "2026-01-01", "partial"),
        ],
        {"new"},
        30,
        "20260621",
    )

    assert [item.event_id for item in selected] == ["new", "recent-partial"]


def test_merge_price_reactions_replaces_refreshed_and_adds_missing_for_new_events():
    events = [event("one", "2026-06-20"), event("two", "2026-06-19")]
    merged = merge_price_reactions(
        [reaction("one", "2026-06-20", "partial")],
        [reaction("one", "2026-06-20", "complete")],
        events,
    )

    assert [(item.event_id, item.data_quality) for item in merged] == [
        ("one", "complete"),
        ("two", "missing"),
    ]


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
        {"stock_code": "005930", "stock_kind": "common"},
        {"stock_code": "123456", "stock_kind": "common"},
    ]
    reactions = [
        {"event_id": "keep"},
        {"event_id": "drop"},
    ]

    filtered = filter_json_dataset_to_supported_markets(companies, events, holdings, reactions)

    assert filtered == (
        [{"stock_code": "005930", "market": "KOSPI"}],
        [{"event_id": "keep", "stock_code": "005930"}],
        [{"stock_code": "005930", "stock_kind": "common"}],
        [{"event_id": "keep"}],
    )
