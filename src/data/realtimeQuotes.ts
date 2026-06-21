import type { LatestPriceSnapshot } from "../types/buybacks";

const DEFAULT_PROXY_BASE_URL = "http://cantabile.tplinkdns.com:3288";
const STOCK_CODE_PATTERN = /^[0-9A-Z]{6}$/;
const UPPER_LIMIT_CODE = "1";
const UP_CODE = "2";
const FLAT_CODE = "3";
const LOWER_LIMIT_CODE = "4";
const DOWN_CODE = "5";

interface NaverFinanceQuotePayload {
  symbol?: string | null;
  summary?: {
    current_price?: number | string | null;
    previous_close?: number | string | null;
    change_pct?: number | string | null;
  } | null;
  raw?: {
    nv?: number | string | null;
    sv?: number | string | null;
    pcv?: number | string | null;
    cr?: number | string | null;
    rf?: number | string | null;
    countOfListedStock?: number | string | null;
  } | null;
  meta?: {
    polled_at?: number | string | null;
  } | null;
}

export async function fetchNaverFinanceQuote(
  stockCode: string
): Promise<LatestPriceSnapshot | null> {
  const normalizedStockCode = stockCode.trim().toUpperCase();
  if (!STOCK_CODE_PATTERN.test(normalizedStockCode)) {
    return null;
  }

  const proxyBaseUrl = naverFinanceProxyBaseUrl();
  if (!proxyBaseUrl) {
    return null;
  }

  const response = await fetch(
    `${proxyBaseUrl}/v1/naverfinance/stocks/${encodeURIComponent(normalizedStockCode)}/quote`,
    { headers: { Accept: "application/json" } }
  );
  if (!response.ok) {
    return null;
  }

  return quoteToLatestPriceSnapshot(
    (await response.json()) as NaverFinanceQuotePayload,
    normalizedStockCode
  );
}

export function quoteToLatestPriceSnapshot(
  payload: NaverFinanceQuotePayload,
  fallbackStockCode = ""
): LatestPriceSnapshot | null {
  const stockCode = (payload.symbol ?? fallbackStockCode).trim().toUpperCase();
  if (!STOCK_CODE_PATTERN.test(stockCode)) {
    return null;
  }

  const close = positiveNumber(payload.summary?.current_price ?? payload.raw?.nv);
  if (close === null) {
    return null;
  }

  const previousClose = positiveNumber(
    payload.summary?.previous_close ?? payload.raw?.sv ?? payload.raw?.pcv
  );
  const changeCode = payload.raw?.rf == null ? null : String(payload.raw.rf);
  const changeRate = normalizedChangeRate(
    numericValue(payload.summary?.change_pct ?? payload.raw?.cr),
    changeCode,
    close,
    previousClose
  );
  const issuedShares = positiveNumber(payload.raw?.countOfListedStock);

  return {
    stock_code: stockCode,
    price_date: dateFromPollTimestamp(payload.meta?.polled_at) ?? today(),
    close,
    source: "naverfinance_proxy",
    change_rate: changeRate,
    issued_shares: issuedShares,
    market_cap_krw: issuedShares === null ? null : close * issuedShares,
    change_code: changeCode
  };
}

function naverFinanceProxyBaseUrl() {
  const configuredUrl =
    import.meta.env.VITE_NAVERFINANCE_PROXY_URL ?? import.meta.env.VITE_KIS_PROXY_URL;
  const baseUrl = String(configuredUrl || DEFAULT_PROXY_BASE_URL).trim().replace(/\/+$/, "");
  if (!baseUrl) {
    return null;
  }
  if (typeof window !== "undefined" && window.location.protocol === "https:" && baseUrl.startsWith("http://")) {
    return null;
  }
  return baseUrl;
}

function normalizedChangeRate(
  changePct: number | null,
  changeCode: string | null,
  close: number,
  previousClose: number | null
) {
  if (changeCode === FLAT_CODE) {
    return 0;
  }
  if (changePct !== null) {
    const absoluteRate = Math.abs(changePct) / 100;
    if (changeCode === LOWER_LIMIT_CODE || changeCode === DOWN_CODE) {
      return -absoluteRate;
    }
    if (changeCode === UPPER_LIMIT_CODE || changeCode === UP_CODE) {
      return absoluteRate;
    }
    return changePct / 100;
  }
  if (previousClose !== null && previousClose > 0) {
    return close / previousClose - 1;
  }
  return null;
}

function positiveNumber(value: number | string | null | undefined) {
  const numeric = numericValue(value);
  return numeric !== null && numeric > 0 ? numeric : null;
}

function numericValue(value: number | string | null | undefined) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const numeric = typeof value === "number" ? value : Number(String(value).replace(/,/g, ""));
  return Number.isFinite(numeric) ? numeric : null;
}

function dateFromPollTimestamp(value: number | string | null | undefined) {
  const timestamp = numericValue(value);
  if (timestamp === null) {
    return null;
  }
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? null : date.toISOString().slice(0, 10);
}

function today() {
  return new Date().toISOString().slice(0, 10);
}
