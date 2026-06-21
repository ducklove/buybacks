# value-invest / buybacks

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

`DART_API_KEY` enables live OpenDART collection. The live build discovers recent buyback disclosures and scans listed companies for share-count / treasury-share snapshots. It then maps DART stock-kind rows to currently trading KOSPI/KOSDAQ stock issues so tradable preferred shares such as `00680K` can be included while non-listed preferred classes are excluded. Without `DART_API_KEY`, the build uses fixture data so the GitHub Pages frontend still builds without browser-side API keys.

`KIS_PROXY_URL` enables price reactions and latest close snapshots. The dashboard keeps event reaction windows separate from latest prices, so market-cap display can use the latest available close even when a recent disclosure does not yet have a post-event reaction window. The dashboard shows both simple returns and KOSPI/KOSDAQ index-relative returns; aggregate return views use the index-relative metric. Current listed-issue filtering uses the Naver mobile stock list, not a paid KRX key. `KRX_AUTH_KEY` is not required.

## Automation

GitHub Pages deployment and live data collection are separate. `Deploy Pages` runs on pushes to `master` and deploys the committed static JSON without calling DART or KIS. `Update buybacks data` runs daily at 05:30 KST, performs an incremental DART/KIS refresh against the committed dataset, commits JSON changes only when data changed, and deploys Pages from the updated static JSON in the same run.
