from scripts.buybacks.fetch_krx_prices import PriceRow, calculate_price_reaction, coerce_price_row


def make_prices(length=70):
    return [
        PriceRow(date=f"2026-01-{day:02d}", close=100 + day, volume=1000 + day * 10)
        for day in range(1, length + 1)
        if day <= 31
    ] + [
        PriceRow(date=f"2026-02-{day:02d}", close=132 + day, volume=1300 + day * 10)
        for day in range(1, 29)
    ] + [
        PriceRow(date=f"2026-03-{day:02d}", close=161 + day, volume=1600 + day * 10)
        for day in range(1, 20)
    ]


def test_calculate_price_reaction_uses_next_trading_day_as_t0():
    reaction = calculate_price_reaction(
        event_id="event-1",
        stock_code="005930",
        event_date="2026-01-10",
        stock_prices=make_prices(),
    )
    assert reaction.close_t0 == 111
    assert round(reaction.return_1d or 0, 6) == round(112 / 111 - 1, 6)
    assert reaction.return_20d is not None
    assert reaction.data_quality == "complete"


def test_calculate_price_reaction_marks_missing_without_future_prices():
    reaction = calculate_price_reaction(
        event_id="event-2",
        stock_code="005930",
        event_date="2026-04-01",
        stock_prices=make_prices(),
    )
    assert reaction.data_quality == "missing"
    assert reaction.close_t0 is None


def test_calculate_price_reaction_marks_partial_with_short_window():
    reaction = calculate_price_reaction(
        event_id="event-3",
        stock_code="005930",
        event_date="2026-03-17",
        stock_prices=make_prices(),
    )
    assert reaction.close_t0 == 179
    assert reaction.return_1d is not None
    assert reaction.return_20d is None
    assert reaction.data_quality == "partial"


def test_coerce_price_row_accepts_kis_proxy_history_fields():
    row = coerce_price_row(
        {
            "stck_bsop_date": "20260620",
            "stck_clpr": "71,200",
            "acml_vol": "12,345,678",
        }
    )

    assert row.date == "2026-06-20"
    assert row.close == 71200
    assert row.volume == 12_345_678
