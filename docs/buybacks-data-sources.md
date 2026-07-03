# Buybacks Data Sources

Last checked: 2026-06-20.

This project builds static JSON files for the browser. API keys stay in local development or GitHub Actions and are never bundled into the frontend.

## OpenDART

OpenDART is the primary source for official disclosure metadata and structured treasury stock disclosure tables.

### Company code mapping

- Official guide: <https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019018>
- Endpoint: `GET https://opendart.fss.or.kr/api/corpCode.xml`
- Output: ZIP/XML with `corp_code`, `corp_name`, `corp_eng_name`, `stock_code`, `modify_date`.
- Pipeline: `scripts/buybacks/fetch_corp_codes.py`
- Use: map OpenDART `corp_code` to the representative listed `stock_code`. The parser accepts 6-character alphanumeric stock codes because some tradable preferred shares use codes such as `00680K`.

### Disclosure search

- Official guide: <https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001>
- Endpoint: `GET https://opendart.fss.or.kr/api/list.json`
- Important parameters: `corp_code`, `bgn_de`, `end_de`, `last_reprt_at`, `pblntf_ty`, `pblntf_detail_ty`, `page_no`, `page_count`.
- Use: discover recent buyback-related candidate companies and capture disclosures that are not covered well by structured APIs, especially retirement announcements.
- Operational limit: when `corp_code` is omitted, OpenDART limits the search period to about three months. The Actions job therefore uses a rolling recent window, caps page count, derives companies directly from recent disclosure rows in `--stock-codes ALL` mode, calls structured decision endpoints only when a company's disclosure names imply that event type, and fetches share-total rows only after treasury-holding rows are available.
- Keywords:
  - `자기주식취득`
  - `자기주식처분`
  - `자기주식취득신탁계약체결`
  - `자기주식취득신탁계약해지`
  - `주식소각결정`
  - `자기주식소각`
  - `주요사항보고서(자기주식취득결정)`
  - `주요사항보고서(자기주식처분결정)`

### Execution result report discovery (E001/E002)

OpenDART has no structured API for treasury stock execution result reports; the DS005 major-report group only covers the four "decision" disclosures. Execution results are therefore discovered through the same `list.json` endpoint with `pblntf_detail_ty` instead of `pblntf_ty`:

- `pblntf_detail_ty=E001` (자기주식취득/처분): `자기주식취득결과보고서`, `자기주식처분결과보고서`
- `pblntf_detail_ty=E002` (신탁계약체결/해지): `신탁계약에의한취득상황보고서`

Only rows whose `report_nm` matches one of the three standardized report forms are kept. Matching normalizes spacing and strips bracket prefixes so `[기재정정]` correction reports (which get a new `rcept_no`) are captured as well. Pipeline entry point: `scripts/buybacks/executions.py` (`fetch_execution_disclosures`).

Note: `classify_event_type` treats any report name containing `결과보고서` or `취득상황보고서` as a non-decision disclosure before all other keyword branches, so result reports can never be double counted as new decision events.

### Execution report body (DART viewer, multi-section)

Result report contents are only available as disclosure viewer HTML (same unofficial dart.fss.or.kr channel already used for retirement details):

1. `GET https://dart.fss.or.kr/dsaf001/main.do?rcpNo=...` returns the viewer shell whose script embeds the full table of contents as repeated `node1['text'|'rcpNo'|'dcmNo'|'eleId'|'offset'|'length'|'dtd']` blocks.
2. Each TOC node is fetched through `GET https://dart.fss.or.kr/report/viewer.do?rcpNo=&dcmNo=&eleId=&offset=&length=&dtd=` (6-8 sections per report, 2-4 KB each) with a polite interval between requests.
3. Sections are merged behind `<!-- SECTION eleId=... text=... -->` markers and cached under `data/raw/buybacks/dart_viewers/{rcept_no}_full.html`, so re-runs are free.

The single-section `fetch_dart_viewer_html` (first `viewDoc` match, cover page only) remains in place for retirement parsing; execution reports need `fetch_dart_viewer_document` because their data lives in later sections.

Parsing is title-based (not positional) because `[기재정정]` reports insert a leading `정 정 신 고 (보고)` section that shifts every section index. Money columns honor the per-table `(단위 : ...)` declaration; some filers report holding/contract tables in 백만원. Parse failures are soft: fields stay null, a warning is recorded in `data_status.json`, and the event pipeline is never blocked.

### Periodic report treasury stock status

- Official guide: <https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2019006>
- Endpoint: `GET https://opendart.fss.or.kr/api/tesstkAcqsDspsSttus.json`
- Required parameters: `corp_code`, `bsns_year`, `reprt_code`.
- Report codes: `11013` first quarter, `11012` half year, `11014` third quarter, `11011` annual report.
- Fields used:
  - `acqs_mth1`, `acqs_mth2`, `acqs_mth3`
  - `stock_knd`
  - `bsis_qy`
  - `change_qy_acqs`
  - `change_qy_dsps`
  - `change_qy_incnr`
  - `trmend_qy`
  - `stlm_dt`
- Output model: `TreasuryHoldingSnapshot`.

### Share count status

- Official guide: <https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2020002>
- Endpoint: `GET https://opendart.fss.or.kr/api/stockTotqySttus.json`
- Fields used: `istc_totqy`, `tesstk_co`, `distb_stock_co`, `stlm_dt`.
- Use: enrich `issued_shares`, `floating_shares`, and treasury holding ratio when available. `tesstkAcqsDspsSttus` does not always provide the denominator needed for ratio calculation, so the pipeline merges stock total rows by stock kind.

### Dividend matters (배당에 관한 사항)

- Official guide: <https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS002&apiId=2019005>
- Endpoint: `GET https://opendart.fss.or.kr/api/alotMatter.json`
- Required parameters: `corp_code`, `bsns_year`, `reprt_code` (annual report `11011` is the only code collected by default; dividends are annual matters).
- Response rows carry a `se` label (구분), an optional `stock_knd` (주식 종류), and `thstrm` (당기) / `frmtrm` (전기) / `lwfr` (전전기) values. Only `thstrm` is stored.
- Rows normalized (label matching is whitespace-insensitive; `DIVIDEND_FIELD_ALIASES` in `scripts/buybacks/fetch_dart_dividends.py` covers response field renames the same way `FIELD_ALIASES` does for buyback decisions):
  - `주당 현금배당금(원)` (보통주 row preferred; explicit 우선주-only rows are dropped) → `dps_common_krw`
  - `현금배당금총액(백만원)` → `cash_dividend_total_krw` (unit multiplier derived from the label, default 백만원 = x1,000,000)
  - `현금배당성향(%)` → `payout_ratio` (0..1 fraction)
  - `(연결)당기순이익(백만원)` (연결 preferred, 별도 fallback) → `net_income_krw`
- Output model: `DividendRecord`, one row per `(corp_code, bsns_year)`, written to `dividends.json` (optional file). Placeholder values (`-`) stay null; a company/year without any parsable row is omitted.
- Scan scope follows the holding-snapshot pattern: `--dividend-stock-codes EVENTS` (default, incremental event companies only), `ALL` (corp code master; roughly one request per listed company per year), or explicit stock codes. Existing records are preserved on every build and merged by key, so occasional `ALL` scans and daily `EVENTS` runs compose safely. Backfill runs never touch `dividends.json`.

### Decision APIs

OpenDART provides structured major-report APIs for treasury stock decision disclosures.

- Treasury stock acquisition decision:
  - Official guide: <https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS005&apiId=2020038>
  - Endpoint: `GET https://opendart.fss.or.kr/api/tsstkAqDecsn.json`
  - Fields normalized: planned shares, planned amount, expected acquisition period, method, purpose, broker, decision date, pre-acquisition holding status.
- Treasury stock disposition decision:
  - Endpoint: `GET https://opendart.fss.or.kr/api/tsstkDpDecsn.json`
  - Fields normalized: planned shares, planned amount, disposition period, method, purpose, broker, decision date, pre-disposition holding status.
- Treasury stock trust contract start:
  - Endpoint: `GET https://opendart.fss.or.kr/api/tsstkAqTrctrCnsDecsn.json`
- Treasury stock trust contract cancellation/end:
  - Endpoint: `GET https://opendart.fss.or.kr/api/tsstkAqTrctrCcDecsn.json`

### Retirement announcements

OpenDART may not expose every stock-retirement announcement through one stable structured endpoint. The MVP therefore:

1. Classifies retirement disclosures through `list.json` report names.
2. Uses `tesstkAcqsDspsSttus.change_qy_incnr` as periodic confirmation when available.
3. Leaves raw XML/HTML parsing as a separate adapter only when a stable official table format is verified.

## kis_proxy Price Data

`kis_proxy` is the project price source for daily stock prices and index returns. It wraps KIS/Naver/Yahoo access behind one server so this repository does not need a paid KRX Open API key.

Required GitHub Actions secrets when price reactions should be populated:

- `KIS_PROXY_URL`: base URL such as `https://example.com:3298`
- `KIS_PROXY_TOKEN`: optional public proxy token sent as `X-KIS-Proxy-Token`

Endpoints used:

- `GET /v1/stocks/{symbol}/history?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&period=D&adjusted=true`
- `GET /v1/indexes/{market}/history?start_date=YYYY-MM-DD&period=D`

The pipeline maps KOSDAQ companies to `market=kosdaq`; all other companies use `market=kospi` for the benchmark return. If `KIS_PROXY_URL` is missing or a proxy request fails, price reaction rows remain present with `data_quality="missing"` and null return fields.

## Current Listed Issue Master

The holding-ratio leaderboard needs currently tradable issues, not just OpenDART stock-kind rows. OpenDART can report preferred or non-voting stock classes that do not have their own listed code. The live pipeline therefore fetches the Naver mobile stock market-value lists for KOSPI and KOSDAQ and keeps only domestic stock issues marked as trading.

Endpoint pattern:

- `GET https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize=100`

Fields used:

- `itemCode`
- `stockName`
- `stockEndType`
- `stockType`
- `tradeStopType`
- `stockExchangeType.nameEng`

This source is used only to map DART holding rows to currently trading listed issue codes. It is not used for price-reaction calculations, which remain on `kis_proxy`.

## KRX Data Marketplace / KRX Open API

KRX remains an optional future source for trading prices, index returns, and potentially treasury execution details.

- Data Marketplace: <https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd?locale=en>
- Open API usage guide: <https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp>
- Daily KOSPI stock trading API example: <https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=JvJFzlAENzZlPBDNGAWC>

Official KRX Open API usage requires:

1. Data Marketplace account and login.
2. API authentication key application.
3. Per-service API usage application and approval.
4. Requests with the authentication key in the `AUTH_KEY` header for documented services.

The KRX page for `유가증권 일별매매정보` states that daily trading data is provided from 2010-01-04 and that the service was recently modified on 2026-01-16. Similar daily APIs exist for KOSDAQ/KONEX and item master data.

### Policy for KRX data

- Do not require `KRX_AUTH_KEY` for the scheduled workflow.
- Use `kis_proxy` for price reactions.
- Use official KRX Open API endpoints only if service approval becomes available later.
- Do not build production scraping against internal web UI calls until terms, robots policy, and stability are confirmed.
- Keep `scripts/buybacks/fetch_krx_prices.py` as the price-source adapter and price-reaction calculation module.
- Keep treasury execution detail as fixture/adapter-only until an official endpoint or license path is confirmed.

Target KRX datasets to confirm:

- `Market Cap excluding treasury stock`
- `Treasury stock acquisition/disposition`
- `Details of treasury stock acquisition/disposition`
- `Price change after disclosure`

## Supporting Sources

KSD/SEIBro can help with security master data and deposit/statistical context, but it is not the primary source for treasury acquisition/disposition event decisions. It should remain optional until the DART/KRX core pipeline is stable.

## Static Output

The frontend reads only:

- `public/data/buybacks/companies.json`
- `public/data/buybacks/events.json`
- `public/data/buybacks/holding_snapshots.json`
- `public/data/buybacks/price_reactions.json`
- `public/data/buybacks/executions.json` (optional; treat a missing file as an empty list)
- `public/data/buybacks/dividends.json` (optional; treat a missing file as an empty list)
- `public/data/buybacks/data_status.json`

`data_status.json` records:

- `generated_at`
- `dart_available`
- `krx_available`
- `price_source`
- `companies_count`
- `events_count`
- `holdings_count`
- `price_reactions_count`
- `executions_count` (when execution tracking has run)
- `dividends_count` (when dividend collection has run)
- `warnings` (includes the stored/unlinked execution report counts)
