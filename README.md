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

`KIS_PROXY_URL` enables price reactions. The KOSPI/KOSDAQ index history used for index-relative returns is fetched once per market over the union of every event window in the build (paged, so old and new events are aligned to the same index rows). Latest close snapshots come from the Naver listing that the build already downloads for the tradable-universe filter (`closePriceRaw`, `fluctuationsRatio`, `marketValueRaw`); kis-proxy is only a fallback for codes the listing does not cover, plus one probe request to date the listing when its rows carry no trade timestamp. The dashboard keeps event reaction windows separate from latest prices, so market-cap display can use the latest available close even when a recent disclosure does not yet have a post-event reaction window. The dashboard shows both simple returns and KOSPI/KOSDAQ index-relative returns; aggregate return views use the index-relative metric. Current listed-issue filtering uses the Naver mobile stock list, not a paid KRX key. `KRX_AUTH_KEY` is not required.

Published dataset arrays are written one compact JSON record per line (about half the bytes of indented JSON, still diffable per record), and `price_reactions.json` ratios are rounded to 6 decimals.

## Automation

GitHub Pages deployment and live data collection are separate. `Deploy Pages` runs on pushes to `master` and deploys the committed static JSON without calling DART or KIS. `Update buybacks data` runs daily at 05:30 KST, performs an incremental DART/KIS refresh against the committed dataset, commits JSON changes only when data changed, and deploys Pages from the updated static JSON in the same run.

Historical event backfills run through the `Backfill buyback events` workflow. Provide a `start` and `end` date in `YYYYMMDD`; the collector splits the range into OpenDART-safe chunks, writes progress percentages to the Actions log and `data/backfills/<run_id>/status.json`, stores collected events in a temporary JSON table, then prepares a pull request with the merged dataset. Review the PR summary for duration, collected events, duplicate events, and new events; merge the PR to accept the backfill.

`Refresh holdings` runs monthly (cron `30 19 1 * *` UTC = the 2nd of the month, 04:30 KST) and on manual dispatch. It calls `build_buybacks_dataset.py` with `--incremental --holding-stock-codes ALL` so every currently listed company's holding snapshot is rescanned and merged into the committed dataset (freshly scanned rows replace stale rows with the same stock/date/report key), while `events.json` keeps the incremental merge semantics: recently discovered events are merged into the existing table, so events older than OpenDART's ~89-day discovery window are preserved instead of being dropped by a full rebuild. It shares the `buybacks-data` concurrency group with `Update buybacks data` to avoid competing commits to `public/data/buybacks`.

### Shrink guard

The data workflows snapshot the committed `public/data/buybacks` before the build and validate with `validate_buybacks_dataset.py --baseline <snapshot>`. Validation fails (so nothing is committed or deployed) when `events.json`, `holding_snapshots.json` or `executions.json` lose more than 2% of their rows versus the snapshot, which protects the history from a partial Naver listing response or an upstream outage. For an intentional cleanup, dispatch the workflow with `allow_shrink: true` (sets `BUYBACKS_ALLOW_SHRINK=1`; the findings are then printed but not enforced).

### Failure notifications

All three data workflows (`Update buybacks data`, `Deploy Pages`, `Backfill buyback events`) and `Refresh holdings` post a failure notification to the `value-invest` hub (`POST {VALUE_INVEST_NOTIFY_URL}/api/internal/notify`) as their last step, gated on `if: failure()`. Configure two repository secrets to enable this:

- `VALUE_INVEST_NOTIFY_URL`: base URL of the value-invest notification endpoint (no trailing path).
- `VALUE_INVEST_INTERNAL_TOKEN`: internal token sent as the `X-Internal-Token` header.

If either secret is empty, the notification step logs a message and exits successfully without calling out, so it is safe to leave them unset.

## Value Compass ecosystem integration (생태계 연동)

Tool id in the hub registry (value-invest `config/ecosystem.json`): **`buybacks`** (integrationKey `buybacks`,
handoff and held-badge enabled).

- **Vendored files (never edit here)**: `public/vc-shell.js`, `public/vc-tokens.css`, the pre-paint theme boot between
  the `<!-- vc:theme-boot -->` markers in `index.html`, the held-badges `?v=` tag and `scripts/buybacks/vc_publish.py`
  are owned by the hub. Change them there, then from this repo root run
  `node ../value-invest/scripts/sync-ecosystem.mjs --write --only buybacks` (without `--write` it only verifies).
- **Ecosystem bar and theme**: `<vc-shell tool="buybacks">` sits outside the React tree (`#root` sibling) with the hub
  link as light-DOM fallback. The topbar toggle calls `VCShell.setTheme` and follows `vc:themechange`; the focused
  company goes to `VCShell.setStock` for the "허브에서 분석" chip. `--price-up`/`--price-down` alias
  `--vc-up`/`--vc-down` (up = red, down = blue) and the body font is `var(--vc-font-sans)`.
- **Inbound deep links** (`src/utils/urlState.ts`, details in [URL deep links](#url-deep-links)):
  - `?stock=<6-char code>` (legacy `?code=` is accepted too) selects the company; `market`, `types`, `year`, `search`
    restore filters. Invalid values fall back to defaults.
  - `?theme=light|dark` applies before first paint without being stored; `?embed` (not `0`/`false`) or `?headless=1`
    sets `html[data-embed]` and hides the topbar and the bar (`?vc-shell=0` or an iframe hides the bar only).
    Both `embed` and `theme` survive the URL rewrite.
  - `#vc-held=code:qty,...` is the holdings snapshot the hub's `/go/buybacks` handoff appends; the badge script
    consumes and removes it.
- **Published summary**: `scripts/buybacks/publish_summary.py --data-dir public/data/buybacks --out-dir public` writes
  `public/summary.json` + `public/version.json` (envelope v1). Vite copies `public/` to the Pages root, so they are
  served at `https://ducklove.github.io/buybacks/summary.json`. The data workflows (`Update buybacks data`,
  `Refresh holdings`, `Backfill buyback events`) run it after validation and commit it with the dataset; `Deploy Pages`
  validates it. Files are rewritten only when the content changes. Payload: latest common-stock treasury ratio per code
  (`ratios`, `ratioAsOf`) plus the top 10, ~23 KB instead of the 1.2 MB `holding_snapshots.json`; the hub falls back to
  that file if the summary fails. Contract:
  [data-contract.md](https://github.com/ducklove/value-invest/blob/master/docs/ecosystem/data-contract.md) §6.4.
- **Hub services used**
  - Held badges: the hub's `/js/portfolio-held-badges.js` adds **보유** badges to `data-portfolio-code` labels.
  - `/api/internal/notify`: every workflow posts failures there (see [Failure notifications](#failure-notifications)).
  - kis-proxy: `KIS_PROXY_URL`/`KIS_PROXY_TOKEN` secrets feed price reactions and latest-price fallback in the data
    build; the same URL is baked in as `VITE_KIS_PROXY_URL` for browser quotes via `/v1/naverfinance/stocks/{code}/quote`.
  - `/api/asset-quotes` and finance-pi are not used.

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

### Dividends / total shareholder return

When `public/data/buybacks/dividends.json` is present, the dashboard joins each stock's latest business-year dividend record (collected from OpenDART `alotMatter.json`, one row per `(corp_code, bsns_year)`) onto its events. The company screener gains two sortable columns: "배당수익률 %" (`cash_dividend_total_krw` / market cap) and "총환원율 %" (`(cash_dividend_total_krw + 최근 12개월 취득계획금액) / market cap`; a stock without a recent buyback plan falls back to the dividend alone). Both show `-` when the market cap or the dividend cash total is unknown, and null values always sort last. The company detail panel adds a "주당배당금/배당수익률" metric (common-share DPS and dividend yield).

`dividends.json` is optional: a missing file (404) falls back to an empty list and the UI renders exactly as before (all dividend cells show `-`). Collection scope is controlled by `build_buybacks_dataset.py --dividend-stock-codes` (`EVENTS` by default — only companies with fresh event disclosures; `ALL` scans the full corp master, roughly one API request per listed company). Existing records are always preserved and merged by `(corp_code, bsns_year)`; backfill runs never touch the file.

### Event study analysis

When `public/data/buybacks/reaction_series.json` and `car_curves.json` are present, the dashboard renders an analysis section ("분석" in the top navigation, right below the dashboard charts) with two panels: a direct-SVG CAR (cumulative abnormal return) curve chart grouped by event type and market (t+1..t+60 trading days, color plus dash pattern per line, event counts in the legend), and a simple backtest panel for the strategy "buy at the first post-disclosure trading day (t0) close, hold N trading days" that reports mean/median/win rate/sample size and a 10-bucket return histogram with event type/market/holding period/return basis/year controls. In index-relative (abnormal) mode an event is excluded from a given holding period when any daily abnormal return inside the window is null, matching the CAR definition. Both files are optional: a missing file (404) falls back to an empty list / `null`, and the section renders an empty-state notice instead — the rest of the app behaves exactly as before until the price-series enrichment pipeline has produced the files. The panel carries a disclaimer that results summarize historical post-disclosure return distributions and exclude transaction costs and slippage.

### Local realtime price proxy

The static dataset (`public/data/buybacks/latest_prices.json`) is enough to run the dashboard locally. To also see realtime price polling in `CompanyDetail`, set `VITE_KIS_PROXY_URL` (or `VITE_NAVERFINANCE_PROXY_URL`, which takes priority) in a local `.env` file to a running `kis_proxy`/Naver Finance proxy instance — see `.env.example`. When neither variable is set, the dashboard silently skips realtime polling and shows only the static latest close.

If the dashboard itself is served over HTTPS, an `http://` proxy URL is treated as mixed content and is disabled automatically (the fetch is skipped rather than left to fail in the browser).
