from scripts.buybacks.build_buybacks_dataset import companies_from_disclosures, parse_stock_codes


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
