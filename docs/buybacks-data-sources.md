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
- Use: map listed 6-digit `stock_code` to 8-digit OpenDART `corp_code`.

### Disclosure search

- Official guide: <https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS001&apiId=2019001>
- Endpoint: `GET https://opendart.fss.or.kr/api/list.json`
- Important parameters: `corp_code`, `bgn_de`, `end_de`, `last_reprt_at`, `pblntf_ty`, `pblntf_detail_ty`, `page_no`, `page_count`.
- Use: discover recent buyback-related candidate companies and capture disclosures that are not covered well by structured APIs, especially retirement announcements.
- Operational limit: when `corp_code` is omitted, OpenDART limits the search period to about three months. The Actions job therefore uses a rolling recent window, caps page count, calls structured decision endpoints only when a company's disclosure names imply that event type, and fetches share-total rows only after treasury-holding rows are available.
- Keywords:
  - `자기주식취득`
  - `자기주식처분`
  - `자기주식취득신탁계약체결`
  - `자기주식취득신탁계약해지`
  - `주식소각결정`
  - `자기주식소각`
  - `주요사항보고서(자기주식취득결정)`
  - `주요사항보고서(자기주식처분결정)`

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

## KRX Data Marketplace / KRX Open API

KRX is the intended source for trading prices, index returns, and potentially treasury execution details.

- Data Marketplace: <https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd?locale=en>
- Open API usage guide: <https://openapi.krx.co.kr/contents/OPP/INFO/OPPINFO003.jsp>
- Daily KOSPI stock trading API example: <https://openapi.krx.co.kr/contents/OPP/USES/service/OPPUSES002_S2.cmd?BO_ID=JvJFzlAENzZlPBDNGAWC>

Official KRX Open API usage requires:

1. Data Marketplace account and login.
2. API authentication key application.
3. Per-service API usage application and approval.
4. Requests with the authentication key in the `AUTH_KEY` header for documented services.

The KRX page for `유가증권 일별매매정보` states that daily trading data is provided from 2010-01-04 and that the service was recently modified on 2026-01-16. Similar daily APIs exist for KOSDAQ/KONEX and item master data.

### MVP policy for KRX data

- Use official KRX Open API endpoints for daily prices and index returns after service approval.
- Do not build production scraping against internal web UI calls until terms, robots policy, and stability are confirmed.
- Keep `scripts/buybacks/fetch_krx_prices.py` as the official API adapter and price-reaction calculation module.
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
- `public/data/buybacks/data_status.json`

`data_status.json` records:

- `generated_at`
- `dart_available`
- `krx_available`
- `companies_count`
- `events_count`
- `holdings_count`
- `price_reactions_count`
- `warnings`
