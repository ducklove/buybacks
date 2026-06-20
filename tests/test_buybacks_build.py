from scripts.buybacks.build_buybacks_dataset import companies_from_disclosures, dedupe_companies, parse_stock_codes
from scripts.buybacks.models import Company


def test_parse_stock_codes_all_uses_disclosure_only_mode():
    assert parse_stock_codes("ALL") is None
    assert parse_stock_codes("005930, 035420") == {"005930", "035420"}


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
