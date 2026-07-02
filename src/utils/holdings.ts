import type { TreasuryHoldingSnapshot } from "../types/buybacks";

/** 보통주로 판별할 stock_kind 키워드 (소문자 비교) */
const COMMON_STOCK_KIND_KEYWORDS = ["보통", "common"] as const;

/** 우선주로 판별할 stock_kind 키워드 (소문자 비교) */
const PREFERRED_STOCK_KIND_KEYWORDS = ["우선", "preferred"] as const;

function includesAny(stockKind: string, keywords: readonly string[]) {
  return keywords.some((keyword) => stockKind.includes(keyword));
}

/** 스냅샷이 보통주 보유분인지 판별합니다. */
export function isCommonHoldingKind(snapshot: TreasuryHoldingSnapshot): boolean {
  return includesAny(snapshot.stock_kind.toLowerCase(), COMMON_STOCK_KIND_KEYWORDS);
}

/** 같은 날짜의 스냅샷 중 어느 것을 우선할지 결정하는 우선순위 (보통주 > 우선주 > 기타). */
export function holdingKindPriority(snapshot: TreasuryHoldingSnapshot): number {
  const stockKind = snapshot.stock_kind.toLowerCase();
  if (includesAny(stockKind, COMMON_STOCK_KIND_KEYWORDS)) return 3;
  if (includesAny(stockKind, PREFERRED_STOCK_KIND_KEYWORDS)) return 2;
  return 1;
}

/** 주식 종류를 정규화한 그룹 키. 보통주는 "common", 우선주는 종류별로 구분합니다. */
export function holdingKindKey(snapshot: TreasuryHoldingSnapshot): string {
  const stockKind = snapshot.stock_kind.trim().replace(/\s+/g, "").toLowerCase();
  if (!stockKind) return "unknown";
  if (includesAny(stockKind, COMMON_STOCK_KIND_KEYWORDS)) return "common";
  if (includesAny(stockKind, PREFERRED_STOCK_KIND_KEYWORDS)) {
    return `preferred:${stockKind}`;
  }
  return stockKind;
}
