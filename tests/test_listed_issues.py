from scripts.buybacks.fetch_listed_issues import parse_naver_listed_issues


def test_parse_naver_listed_issues_keeps_trading_stock_issues_with_alpha_codes():
    issues = parse_naver_listed_issues(
        {
            "stocks": [
                {
                    "stockType": "domestic",
                    "stockEndType": "stock",
                    "itemCode": "00680K",
                    "stockName": "미래에셋증권2우B",
                    "tradeStopType": {"code": "1", "name": "TRADING"},
                    "stockExchangeType": {"nameEng": "KOSPI"},
                },
                {
                    "stockType": "domestic",
                    "stockEndType": "etf",
                    "itemCode": "ETF001",
                    "stockName": "ETF",
                    "tradeStopType": {"code": "1", "name": "TRADING"},
                    "stockExchangeType": {"nameEng": "KOSPI"},
                },
            ]
        },
        "KOSPI",
    )

    assert len(issues) == 1
    assert issues[0].stock_code == "00680K"
    assert issues[0].issue_name == "미래에셋증권2우B"
    assert issues[0].is_trading is True
