import scripts.buybacks.fetch_dart_dividends as dart_dividends
from scripts.buybacks.dart_client import OpenDartError, OpenDartNoData
from scripts.buybacks.fetch_dart_dividends import (
    classify_dividend_row,
    collect_dividend_records,
    dividend_coverage_warnings,
    merge_dividends,
    normalize_dividend_record,
    unit_multiplier_from_label,
)
from scripts.buybacks.models import Company, DividendRecord


def company(corp_code: str = "00126380", stock_code: str = "005930", name: str = "삼성전자") -> Company:
    return Company(corp_code, stock_code, name, "KOSPI", None, "2026-06-30")


def dividend_record(corp_code: str, bsns_year: int, dps: int | None = 1000) -> DividendRecord:
    return DividendRecord(
        corp_code=corp_code,
        stock_code="005930",
        corp_name="삼성전자",
        bsns_year=bsns_year,
        report_code="11011",
        dps_common_krw=dps,
        cash_dividend_total_krw=None,
        payout_ratio=None,
        net_income_krw=None,
        rcept_no=None,
    )


def alot_rows() -> list[dict]:
    return [
        {"rcept_no": "20260310000001", "corp_name": "삼성전자", "se": "주당액면가액(원)", "thstrm": "100"},
        {"se": "(연결)당기순이익(백만원)", "thstrm": "34,451,351"},
        {"se": "(별도)당기순이익(백만원)", "thstrm": "25,397,099"},
        {"se": "(연결)주당순이익(원)", "thstrm": "5,777"},
        {"se": "주당 현금배당금(원)", "stock_knd": "보통주식", "thstrm": "1,444"},
        {"se": "주당 현금배당금(원)", "stock_knd": "우선주식", "thstrm": "1,445"},
        {"se": "현금배당금총액(백만원)", "thstrm": "9,809,438"},
        {"se": "현금배당성향(%)", "thstrm": "28.5"},
        {"se": "현금배당수익률(%)", "stock_knd": "보통주식", "thstrm": "2.5"},
    ]


def test_classify_dividend_row_matches_only_stored_rows():
    assert classify_dividend_row("주당 현금배당금(원)") == "dps"
    assert classify_dividend_row("현금배당금총액(백만원)") == "cash_dividend_total"
    assert classify_dividend_row("현금배당성향(%)") == "payout_ratio"
    assert classify_dividend_row("(연결)당기순이익(백만원)") == "net_income"
    assert classify_dividend_row("현금배당수익률(%)") is None
    assert classify_dividend_row("(연결)주당순이익(원)") is None
    assert classify_dividend_row("주당액면가액(원)") is None
    assert classify_dividend_row(None) is None


def test_unit_multiplier_prefers_specific_tokens_over_bare_won():
    assert unit_multiplier_from_label("현금배당금총액(백만원)", 1) == 1_000_000
    assert unit_multiplier_from_label("현금배당금총액(천원)", 1) == 1_000
    assert unit_multiplier_from_label("현금배당금총액(억원)", 1) == 100_000_000
    assert unit_multiplier_from_label("주당 현금배당금(원)", 1_000_000) == 1
    assert unit_multiplier_from_label("현금배당성향(%)", 7) == 7


def test_normalize_applies_million_won_multiplier_and_percent_ratio():
    record = normalize_dividend_record(alot_rows(), company(), 2025, "11011")

    assert record is not None
    assert record.dps_common_krw == 1_444
    assert record.cash_dividend_total_krw == 9_809_438_000_000
    assert record.payout_ratio == 0.285
    assert record.net_income_krw == 34_451_351_000_000
    assert record.rcept_no == "20260310000001"
    assert record.bsns_year == 2025
    assert record.report_code == "11011"


def test_normalize_prefers_common_share_dps_over_preferred():
    record = normalize_dividend_record(alot_rows(), company(), 2025, "11011")
    assert record is not None
    assert record.dps_common_krw == 1_444  # not the 우선주 1,445


def test_normalize_keeps_kindless_dps_row_but_drops_preferred_only_rows():
    kindless = [{"se": "주당 현금배당금(원)", "thstrm": "500"}]
    record = normalize_dividend_record(kindless, company(), 2025, "11011")
    assert record is not None and record.dps_common_krw == 500

    preferred_only = [{"se": "주당 현금배당금(원)", "stock_knd": "우선주식", "thstrm": "700"}]
    record = normalize_dividend_record(preferred_only, company(), 2025, "11011")
    assert record is None  # common dividend unknown and no other field present


def test_normalize_prefers_consolidated_net_income_with_separate_fallback():
    consolidated = normalize_dividend_record(
        [
            {"se": "(별도)당기순이익(백만원)", "thstrm": "100"},
            {"se": "(연결)당기순이익(백만원)", "thstrm": "200"},
        ],
        company(),
        2025,
        "11011",
    )
    assert consolidated is not None and consolidated.net_income_krw == 200_000_000

    separate_only = normalize_dividend_record(
        [{"se": "(별도)당기순이익(백만원)", "thstrm": "△100"}],
        company(),
        2025,
        "11011",
    )
    assert separate_only is not None and separate_only.net_income_krw == -100_000_000


def test_normalize_treats_dash_placeholders_as_missing():
    rows = [
        {"se": "주당 현금배당금(원)", "stock_knd": "보통주식", "thstrm": "-"},
        {"se": "현금배당금총액(백만원)", "thstrm": "-"},
        {"se": "현금배당성향(%)", "thstrm": "-"},
    ]
    assert normalize_dividend_record(rows, company(), 2025, "11011") is None


def test_normalize_falls_back_to_alias_value_field_names():
    rows = [{"se": "주당 현금배당금(원)", "stock_knd": "보통주식", "thstrm_amount": "1,000"}]
    record = normalize_dividend_record(rows, company(), 2025, "11011")
    assert record is not None
    assert record.dps_common_krw == 1_000


def test_merge_dividends_replaces_same_key_and_keeps_other_years():
    existing = [dividend_record("00126380", 2024, dps=1400), dividend_record("00126380", 2025, dps=1)]
    incoming = [dividend_record("00126380", 2025, dps=1444)]

    merged = merge_dividends(existing, incoming)

    assert [(item.bsns_year, item.dps_common_krw) for item in merged] == [(2024, 1400), (2025, 1444)]


def test_dividend_coverage_warnings_flags_mostly_empty_records():
    empty = dividend_record("00126380", 2025, dps=None)
    filled = dividend_record("00164779", 2025, dps=1000)

    assert dividend_coverage_warnings([]) == []
    assert dividend_coverage_warnings([filled, filled, empty]) == []
    warnings = dividend_coverage_warnings([empty, empty, filled])
    assert len(warnings) == 1
    assert "DIVIDEND_FIELD_ALIASES" in warnings[0]


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.calls: list[tuple[str, str, str]] = []

    def request_json(self, endpoint: str, params: dict) -> dict:
        key = (params["corp_code"], params["bsns_year"], params["reprt_code"])
        self.calls.append(key)
        result = self.responses.get(key)
        if result is None:
            raise OpenDartNoData("013 no data")
        if isinstance(result, Exception):
            raise result
        return result


def test_collect_dividend_records_uses_first_report_code_and_collects_warnings(monkeypatch):
    samsung = company()
    naver = company("00266961", "035420", "NAVER")
    broken = company("00164779", "000660", "SK하이닉스")
    fake = FakeClient(
        {
            ("00126380", "2025", "11011"): {"status": "000", "list": alot_rows()},
            # NAVER: annual report missing, half-year report carries the data.
            ("00266961", "2025", "11012"): {
                "status": "000",
                "list": [{"se": "주당 현금배당금(원)", "stock_knd": "보통주식", "thstrm": "10"}],
            },
            ("00164779", "2025", "11011"): OpenDartError("status=020 rate limited"),
        }
    )
    monkeypatch.setattr(dart_dividends, "OpenDartClient", lambda api_key, raw_dir=None: fake)

    records, warnings = collect_dividend_records(
        "key",
        [samsung, naver, broken],
        years=[2025],
        report_codes=["11011", "11012"],
    )

    by_corp = {record.corp_code: record for record in records}
    assert set(by_corp) == {"00126380", "00266961"}
    # First report code with data wins: Samsung never touches 11012.
    assert ("00126380", "2025", "11012") not in fake.calls
    assert by_corp["00266961"].report_code == "11012"
    assert any("000660 dividends 2025/11011 failed" in warning for warning in warnings)
