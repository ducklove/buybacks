# Buybacks fixtures

These files are synthetic development fixtures. They keep the static frontend buildable when `DART_API_KEY` and `KIS_PROXY_URL` are not available. Do not treat the values as verified market data.

`executions.json` holds synthetic execution result reports (BuybackExecution rows). Three rows are linked to fixture events through `linked_event_id` (`fixture-005930-2026-05-22-acq`, `fixture-035420-2026-05-12-dispose`, `fixture-005380-2026-04-29-acq`) so frontend join logic can be developed against them, and one row stays `unlinked` to exercise the unlinked-report path.
