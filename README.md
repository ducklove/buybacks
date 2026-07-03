# Buybacks

Static MVP for exploring Korean treasury stock acquisition, disposition, retirement, and holding data.

## Commands

```bash
npm install
npm run build:data
npm run update:data
npm run validate:data
npm run test
npm run build
python -m pytest
```

Development environment: Node 24 and Python 3.12+ (matches the `actions/setup-node` and `actions/setup-python` versions pinned in `.github/workflows/`). Install Python test dependencies with `pip install -r requirements.txt` (the pipeline itself uses only the standard library; `pytest` is only needed to run `tests/`).

`DART_API_KEY` enables live OpenDART collection. The live build discovers recent buyback disclosures and scans listed companies for share-count / treasury-share snapshots. It then maps DART stock-kind rows to currently trading KOSPI/KOSDAQ stock issues so tradable preferred shares such as `00680K` can be included while non-listed preferred classes are excluded. Without `DART_API_KEY`, the build uses fixture data so the GitHub Pages frontend still builds without browser-side API keys.

`KIS_PROXY_URL` enables price reactions and latest close snapshots. The dashboard keeps event reaction windows separate from latest prices, so market-cap display can use the latest available close even when a recent disclosure does not yet have a post-event reaction window. The dashboard shows both simple returns and KOSPI/KOSDAQ index-relative returns; aggregate return views use the index-relative metric. Current listed-issue filtering uses the Naver mobile stock list, not a paid KRX key. `KRX_AUTH_KEY` is not required.

## Automation

GitHub Pages deployment and live data collection are separate. `Deploy Pages` runs on pushes to `master` and deploys the committed static JSON without calling DART or KIS. `Update buybacks data` runs daily at 05:30 KST, performs an incremental DART/KIS refresh against the committed dataset, commits JSON changes only when data changed, and deploys Pages from the updated static JSON in the same run.

Historical event backfills run through the `Backfill buyback events` workflow. Provide a `start` and `end` date in `YYYYMMDD`; the collector splits the range into OpenDART-safe chunks, writes progress percentages to the Actions log and `data/backfills/<run_id>/status.json`, stores collected events in a temporary JSON table, then prepares a pull request with the merged dataset. Review the PR summary for duration, collected events, duplicate events, and new events; merge the PR to accept the backfill.

`Refresh holdings` runs monthly (1st of the month, 04:30 KST) and on manual dispatch. It calls `build_buybacks_dataset.py` with `--incremental --holding-stock-codes ALL` so every currently listed company's holding snapshot is rescanned and merged into the committed dataset (freshly scanned rows replace stale rows with the same stock/date/report key), while `events.json` keeps the incremental merge semantics: recently discovered events are merged into the existing table, so events older than OpenDART's ~89-day discovery window are preserved instead of being dropped by a full rebuild. It shares the `buybacks-data` concurrency group with `Update buybacks data` to avoid competing commits to `public/data/buybacks`.

### Failure notifications

All three data workflows (`Update buybacks data`, `Deploy Pages`, `Backfill buyback events`) and `Refresh holdings` post a failure notification to the `value-invest` hub (`POST {VALUE_INVEST_NOTIFY_URL}/api/internal/notify`) as their last step, gated on `if: failure()`. Configure two repository secrets to enable this:

- `VALUE_INVEST_NOTIFY_URL`: base URL of the value-invest notification endpoint (no trailing path).
- `VALUE_INVEST_INTERNAL_TOKEN`: internal token sent as the `X-Internal-Token` header.

If either secret is empty, the notification step logs a message and exits successfully without calling out, so it is safe to leave them unset.

## Frontend

### URL deep links

The dashboard mirrors its filter and selection state into the URL query string (`src/utils/urlState.ts`), so a link can be shared to reproduce a specific view. Supported parameters:

- `market`: `KOSPI` or `KOSDAQ` (omit or use an unrecognized value for all markets).
- `types`: comma-separated event types, e.g. `direct_acquisition,retirement`.
- `year`: 4-digit disclosure year, e.g. `2025`.
- `search`: free-text search across company name and stock code.
- `stock`: 6-character stock code to preselect in the company detail panel.

Example: `?market=KOSDAQ&types=direct_acquisition,retirement&year=2025&search=삼성&stock=005930`.

Invalid or malformed values (wrong market name, non-4-digit year, malformed stock code, unknown event type) silently fall back to their defaults instead of erroring, and the URL is rewritten to drop parameters that match the default state.

### Execution / completion tracking

When `public/data/buybacks/executions.json` is present, the dashboard joins buyback execution reports (acquisition/disposition result reports and trust-contract status reports) onto their linked events via `linked_event_id`. `executions.json` is optional: a missing file (404) falls back to an empty list, and the UI renders exactly as it does today (the completion column shows `-`).

Each event can have zero or many linked executions (trust contracts report status quarterly); the dashboard picks one representative execution per event — the latest `as_of_date` for trust status reports (trust progress is cumulative, so rows are never summed) and the latest `disclosure_date` otherwise (so a later correction report supersedes the original). The completion rate prefers actual/planned **share count**, falls back to actual/planned **amount** (event-level planned amount first, then the execution's own), and uses `trust_progress_ratio` directly for trust contracts. Status is "완료" (complete) when `shortfall` is `false`, "미달" (shortfall, with the reason shown in a tooltip) when `shortfall` is `true`, "진행중" (in progress) for trust status reports, and no badge when the result report hasn't arrived yet or the execution can't be linked.

The event table's sortable "이행률" (completion rate) column and the company detail panel's per-event execution summary (actual shares/amount, completion rate, and — for trust contracts — a progress meter with as-of date) both use this join. Execution reports that could not be linked to a known event (`link_method: "unlinked"`) are never shown on the event table; they appear only in a separate "미연결 결과보고서" subsection of the company detail panel, matched by stock code.

### Local realtime price proxy

The static dataset (`public/data/buybacks/latest_prices.json`) is enough to run the dashboard locally. To also see realtime price polling in `CompanyDetail`, set `VITE_KIS_PROXY_URL` (or `VITE_NAVERFINANCE_PROXY_URL`, which takes priority) in a local `.env` file to a running `kis_proxy`/Naver Finance proxy instance — see `.env.example`. When neither variable is set, the dashboard silently skips realtime polling and shows only the static latest close.

If the dashboard itself is served over HTTPS, an `http://` proxy URL is treated as mixed content and is disabled automatically (the fetch is skipped rather than left to fail in the browser).
