import type { DataQuality, EventType, Market } from "../types/buybacks";

export const EVENT_TYPE_LABELS: Record<EventType, string> = {
  direct_acquisition: "직접취득",
  direct_disposition: "직접처분",
  trust_contract_start: "신탁체결",
  trust_contract_end: "신탁해지",
  retirement: "소각",
  periodic_holding_update: "보유현황",
  unknown: "미분류"
};

export const MARKET_LABELS: Record<Market, string> = {
  KOSPI: "KOSPI",
  KOSDAQ: "KOSDAQ",
  KONEX: "KONEX",
  OTHER: "기타"
};

export const DATA_QUALITY_LABELS: Record<DataQuality, string> = {
  complete: "완전",
  partial: "부분",
  missing: "결측"
};

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return new Intl.NumberFormat("ko-KR").format(value);
}

export function formatKRW(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  const abs = Math.abs(value);
  if (abs >= 1_0000_0000_0000) return `${formatNumber(Math.round(value / 1_0000_0000_0000))}조`;
  if (abs >= 1_0000_0000) return `${formatNumber(Math.round(value / 1_0000_0000))}억`;
  return formatNumber(value);
}

export function formatMarketCapKRW(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  const abs = Math.abs(value);
  if (abs >= 1_0000_0000_0000) {
    return `${formatNumber(Math.round((value / 1_0000_0000_0000) * 10) / 10)}조`;
  }
  if (abs >= 1_0000_0000) return `${formatNumber(Math.round(value / 1_0000_0000))}억`;
  return formatNumber(value);
}

export function formatPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatSignedPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  const percent = value * 100;
  return `${percent > 0 ? "+" : ""}${percent.toFixed(digits)}%`;
}

export function dartUrl(rceptNo: string | null): string | null {
  return rceptNo ? `https://dart.fss.or.kr/dsaf001/main.do?rcpNo=${rceptNo}` : null;
}
