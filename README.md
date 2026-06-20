# value-invest / buybacks

Static MVP for exploring Korean treasury stock acquisition, disposition, retirement, and holding data.

## Commands

```bash
npm install
npm run build:data
npm run validate:data
npm run test
npm run build
python -m pytest
```

`DART_API_KEY` enables live OpenDART collection. The live build discovers recent buyback disclosures and scans listed companies for share-count / treasury-share snapshots so the top holding-ratio chart is based on the full available listed-company universe. Without `DART_API_KEY`, the build uses fixture data so the GitHub Pages frontend still builds without browser-side API keys.

`KIS_PROXY_URL` enables price reactions. `KRX_AUTH_KEY` is not required.
