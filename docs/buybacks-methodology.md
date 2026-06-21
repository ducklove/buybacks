# Buybacks Methodology

This MVP is a data exploration tool, not investment advice. It avoids labels such as "good news" or "bad news" and keeps missing data visible.

## Normalized Models

### Company

Maps OpenDART company identity to the listed stock code used by KRX and the frontend.
Generated live datasets are restricted to OpenDART market-classified KOSPI/KOSDAQ companies that have at least one event or holding row in the output dataset.

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

### TreasuryHoldingSnapshot

One row per company/report period/stock kind. The preferred ratio is:

```text
ending treasury shares / issued shares
```

If the share-count denominator is missing or from a mismatched date, the output keeps `treasury_ratio` null or marks downstream status as partial.

### PriceReaction

Price reaction is calculated from the first trading day after the event date.

```text
t0 = first trading day after event_date
return_Nd = close(t0 + N trading days) / close(t0) - 1
abnormal_return_20d = return_20d - market_return_20d
```

The frontend shows both simple return and index-relative return. Summary cards, sorting, and return distribution charts use `abnormal_return_20d` as the representative return metric.

If trading is suspended, delisted, or the required future window is not available, the metric remains null and `data_quality` becomes `partial` or `missing`.

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

Preferred completion rate:

```text
actual_shares / planned_shares_common
```

Actual execution data may require KRX or follow-up disclosure coverage. Without verified execution data, completion rate stays null.

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

The default live discovery window is the last 89 days because OpenDART `list.json` without `corp_code` is limited to roughly three months. The scheduled workflow uses disclosure-discovered companies for event enrichment (`--stock-codes ALL`) and scans all listed companies for the latest annual-report share-count snapshots (`--holding-stock-codes ALL`, `--holding-source stock_totals`, `--report-codes 11011`). The output is then narrowed to KOSPI/KOSDAQ market-classified companies with event or holding rows. This keeps the top holding-ratio chart based on actual treasury-share ratios across the available KOSPI/KOSDAQ universe instead of only recent disclosure candidates. Historical backfills should widen `--report-codes` or run `--holding-source treasury_tables` in a separate controlled job when acquisition/disposition flow fields are needed.

Price reactions use `kis_proxy` when `KIS_PROXY_URL` is configured. If the proxy is unavailable, the dataset keeps price reaction rows with null metrics and `data_quality="missing"` rather than substituting an unofficial external API.
