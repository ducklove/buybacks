# Buybacks Methodology

This MVP is a data exploration tool, not investment advice. It avoids labels such as "good news" or "bad news" and keeps missing data visible.

## Normalized Models

### Company

Maps OpenDART company identity to the listed stock code used by the frontend. Generated live datasets are restricted to currently trading KOSPI/KOSDAQ stock issues that have at least one event or holding row in the output dataset.

### BuybackEvent

One normalized row per disclosure or derived event. Event types:

- `direct_acquisition`
- `direct_disposition`
- `trust_contract_start`
- `trust_contract_end`
- `retirement`
- `periodic_holding_update`
- `unknown`

`event_id` is deterministic from source, receipt number or stock/date fallback, and event type.

### BuybackExecution

One row per execution result report, stored separately in `executions.json` (joined like `price_reactions.json` instead of mutating event rows). Execution types:

- `acquisition_result` (자기주식취득결과보고서)
- `disposition_result` (자기주식처분결과보고서)
- `trust_status` (신탁계약에의한취득상황보고서, recurring roughly every 3 months per contract with cumulative figures)

`execution_id` is `dart-{rcept_no}-{execution_type}`. Key fields: actual order/fill share counts and amounts from the "계" total row, the report's own planned amount/shares from the 일치·미달 여부 table, `shortfall`/`shortfall_reason`, post-execution holding quantity/ratio, and for trust reports the contract amount plus `trust_progress_ratio` (누적 취득금액 / 계약금액).

Linking rules (recomputed deterministically on every build so backfilled events pick up their reports):

1. `report_date`: `corp_code` + 본문의 "주요사항보고서 제출일" == 결정 이벤트의 `disclosure_date` + event-type mapping (`acquisition_result`→`direct_acquisition`, `disposition_result`→`direct_disposition`, `trust_status`→`trust_contract_start`).
2. `period_overlap`: fallback when the referenced date misses (e.g. the origin disclosure was re-filed) — same corp and mapped type, execution period overlapping the decision's period, nearest preceding disclosure wins.
3. `unlinked`: preserved, never dropped. Expected when the originating decision predates the discovery window or a backfill has not reached it yet; `data_status.json` reports the unlinked count.

Correction handling: a `[기재정정]` result report has a new `rcept_no` and supersedes the original within its `(corp_code, execution_type, origin_report_date)` group (trust reports add `as_of_date` to that group so quarterly history survives). Because trust figures are cumulative, aggregations must use one representative row per contract — the latest `as_of_date` — via `latest_trust_status_by_contract`.

### TreasuryHoldingSnapshot

One row per company/report period/stock kind. The preferred ratio is:

```text
ending treasury shares / issued shares
```

If the share-count denominator is missing or from a mismatched date, the output keeps `treasury_ratio` null or marks downstream status as partial.

OpenDART reports stock-kind rows such as common stock, preferred stock, and non-voting stock. Before writing the live dataset, those rows are matched against the current listed-issue master. Tradable preferred shares with their own listed code are kept under that issue code, while stock-kind rows that cannot be matched to a currently trading KOSPI/KOSDAQ issue are excluded from top holding-ratio views.

### PriceReaction

Price reaction is calculated from the first trading day after the event date.

```text
t0 = first trading day after event_date
return_Nd = close(t0 + N trading days) / close(t0) - 1
abnormal_return_20d = return_20d - market_return_20d
```

The frontend shows both simple return and index-relative return. Summary cards, sorting, and return distribution charts use `abnormal_return_20d` as the representative return metric.

If trading is suspended, delisted, or the required future window is not available, the metric remains null and `data_quality` becomes `partial` or `missing`.

### ReactionSeries (reaction_series.json, optional)

The daily post-event return series preserved for event-study CAR curves and frontend backtests. It is produced on the same computation path (and the same fetched price rows) as PriceReaction, so both share the identical t0 definition.

```text
t0 = first trading day after event_date (same as PriceReaction)
daily_return[k]   = close(t+k+1) / close(t+k) - 1        # per trading day, NOT cumulative vs t0
daily_abnormal[k] = daily_return[k] - index_daily_return[k]
```

- Arrays cover t+1..t+60 trading days at most; the length is the number of trading days available so far (0..60). Values are rounded to 6 decimals.
- `daily_abnormal` has the same length as `daily_return` and uses the same index selection as the `abnormal_return_Nd` snapshot fields (KOSPI or KOSDAQ index via kis_proxy) with the same positional trading-day alignment from the index's own t0. Entries are null where the index data is unavailable.
- `data_quality` is `complete` when all 60 days exist, otherwise `partial`. Events with no post-event price data at all get no series record (there is no `missing` placeholder row).
- Incremental builds merge by `event_id`: a recalculated event replaces its series, series of deduped/removed events are dropped, and an event whose recalculation produced no series keeps its previous series (historical daily returns cannot change).
- The daily scheduled run only recalculates the usual recent window (`--price-reaction-scope recent`). `--price-reaction-scope missing-series` additionally recalculates events that have a reaction but no stored series (one-off backfill), and `--price-reaction-scope all` recalculates every event.

### CAR curves (car_curves.json, optional)

Mean cumulative abnormal return curves aggregated per `event_type` x market group (`ALL`, `KOSPI`, `KOSDAQ`). This file is a pure derivative: it is re-aggregated from `reaction_series.json` + `events.json` on every build and never merged with a previously stored aggregate.

```text
CAR_k(event)     = sum(daily_abnormal[0..k])             # cumulative sum, stops at the first null entry
mean_car[k]      = mean of CAR_k over the group's events that still have data at k
```

- `mean_car` always has length `window` (60); entries are null at depths where no event in the group has data.
- Events with a shorter series simply drop out of deeper `k` buckets instead of being zero-filled; `n` counts the group's events contributing at least one abnormal data point.
- Groups with fewer than `min_events` (5) contributing events are omitted.

Both files are optional: datasets built before series tracking keep validating cleanly, and `data_status.json` reports `reaction_series_count`, `car_groups_count`, plus a warning with the number of events that still lack a series.

## Event Scale

Preferred event scale:

```text
planned_amount_krw / market_cap
```

If market cap is not available, the fallback is:

```text
planned_shares_common * reference_close / market_cap
```

If neither denominator is reliable, event scale stays null.

## Completion Rate

Completion rate is derived at display/aggregation time from a linked BuybackExecution — it is intentionally not stored, so a corrected decision event can never disagree with a stale stored ratio. Derivation order:

1. Share-count basis (preferred): `execution.actual_shares / event.planned_shares_common`. Amount-based "미달" verdicts can coexist with a 100% share fill (e.g. the plan's share count was fully acquired below the budgeted amount), so share counts win.
2. Amount fallback: `execution.actual_amount_krw / (event.planned_amount_krw or execution.planned_amount_krw)` when share counts are unavailable.
3. Trust contracts: `execution.trust_progress_ratio` (누적 취득금액 / 신탁계약금액) from the latest 상황보고서 per contract (`latest_trust_status_by_contract`); quarterly rows must never be summed because they are cumulative.

Events without a linked execution report (not yet due, unlinked, or before execution tracking) keep a null completion rate. `validate_buybacks_dataset.py` reports derived rates above 1.2 as non-blocking warnings.

## Data Quality Rules

- Do not coerce missing returns to zero.
- Parse `"-"`, empty strings, and "해당사항 없음" as null.
- Preserve raw DART responses under `data/raw/buybacks/` for debugging when live collection runs.
- Keep `data/raw/` ignored by Git to avoid storing large API payloads.
- Fixture data is synthetic and exists only to keep development and GitHub Pages builds reproducible without secrets.

## Update Flow

Fixture build:

```bash
npm run build:data
npm run validate:data
```

Live OpenDART build:

```bash
$env:DART_API_KEY = "..."
python scripts/buybacks/build_buybacks_dataset.py --live-if-available --output public/data/buybacks
python scripts/buybacks/validate_buybacks_dataset.py public/data/buybacks
```

GitHub Actions live build:

1. Register `DART_API_KEY` in repository Actions secrets.
2. Run `Update buybacks data and deploy Pages`.
3. The workflow fetches `corpCode.xml`, searches recent major-report disclosures for buyback-related report names, calls structured decision APIs for discovered event companies, scans listed companies for `stockTotqySttus` share-count snapshots, then builds the static Vite site.

The default live discovery window is the last 89 days because OpenDART `list.json` without `corp_code` is limited to roughly three months. The scheduled workflow uses disclosure-discovered companies for event enrichment (`--stock-codes ALL`) and scans all listed companies for the latest annual-report share-count snapshots (`--holding-stock-codes ALL`, `--holding-source stock_totals`, `--report-codes 11011`). The output is then narrowed to currently trading KOSPI/KOSDAQ issues using the listed-issue master (`--listed-issue-source naver`). This keeps the top holding-ratio chart based on actual treasury-share ratios across tradable issues instead of only recent disclosure candidates or non-listed stock classes. Historical backfills should widen `--report-codes` or run `--holding-source treasury_tables` in a separate controlled job when acquisition/disposition flow fields are needed.

Price reactions use `kis_proxy` when `KIS_PROXY_URL` is configured. If the proxy is unavailable, the dataset keeps price reaction rows with null metrics and `data_quality="missing"` rather than substituting an unofficial external API.
