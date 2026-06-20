from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from .models import EventType, Market

MISSING_VALUES = {"", "-", "－", "—", "N/A", "n/a", "nan", "NaN", "해당사항없음", "해당사항 없음"}
DATE_RE = re.compile(r"(\d{4})[.\-/년\s]*(\d{1,2})[.\-/월\s]*(\d{1,2})")


def parse_number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return value

    text = str(value).strip()
    if text in MISSING_VALUES:
        return None
    text = text.replace(",", "").replace(" ", "")
    text = text.replace("△", "-").replace("▲", "-")
    text = text.rstrip("%")
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    if text in MISSING_VALUES:
        return None
    try:
        number = float(text) if "." in text else int(text)
    except ValueError:
        return None
    return number


def parse_ratio_percent(value: Any) -> float | None:
    number = parse_number(value)
    if number is None:
        return None
    return float(number) / 100


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = str(value).strip()
    if text in MISSING_VALUES:
        return None
    if re.fullmatch(r"\d{8}", text):
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    match = DATE_RE.search(text)
    if not match:
        return None
    year, month, day = match.groups()
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def market_from_corp_cls(value: str | None) -> Market:
    return {
        "Y": "KOSPI",
        "K": "KOSDAQ",
        "N": "KONEX",
        "E": "OTHER",
    }.get((value or "").strip().upper(), "OTHER")


def classify_event_type(report_name: str | None) -> EventType:
    text = report_name or ""
    if "신탁계약해지" in text or "신탁계약 해지" in text:
        return "trust_contract_end"
    if "신탁계약체결" in text or "신탁계약 체결" in text:
        return "trust_contract_start"
    if "처분" in text:
        return "direct_disposition"
    if "소각" in text or "주식소각" in text:
        return "retirement"
    if "취득" in text:
        return "direct_acquisition"
    if "자기주식" in text and "현황" in text:
        return "periodic_holding_update"
    return "unknown"


def event_id(source: str, rcept_no: str | None, stock_code: str, event_type: EventType, disclosure_date: str) -> str:
    key = rcept_no or f"{stock_code}-{disclosure_date}"
    return f"{source.lower()}-{key}-{event_type}"


def dart_source_url(rcept_no: str | None) -> str | None:
    if not rcept_no:
        return None
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"

