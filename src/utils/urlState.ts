import { EVENT_TYPES, type EventType, type Filters } from "../types/buybacks";
import { DEFAULT_FILTERS, marketOptions } from "./metrics";

export interface UrlAppState {
  filters: Filters;
  selectedStockCode: string | null;
}

const PARAM_MARKET = "market";
const PARAM_EVENT_TYPES = "types";
const PARAM_YEAR = "year";
const PARAM_SEARCH = "search";
const PARAM_STOCK = "stock";

const YEAR_PATTERN = /^\d{4}$/;
const STOCK_CODE_PATTERN = /^[0-9A-Z]{6}$/;

function isEventType(value: string): value is EventType {
  return (EVENT_TYPES as readonly string[]).includes(value);
}

function parseMarket(value: string | null): Filters["market"] {
  if (value === null) return DEFAULT_FILTERS.market;
  const allowed = marketOptions();
  return allowed.includes(value as Filters["market"])
    ? (value as Filters["market"])
    : DEFAULT_FILTERS.market;
}

function parseEventTypes(value: string | null): EventType[] {
  if (value === null) return [...DEFAULT_FILTERS.eventTypes];
  const seen = new Set<EventType>();
  value
    .split(",")
    .map((item) => item.trim())
    .filter(isEventType)
    .forEach((item) => seen.add(item));
  return Array.from(seen);
}

function parseYear(value: string | null): string {
  if (value === null || !YEAR_PATTERN.test(value)) return DEFAULT_FILTERS.year;
  return value;
}

function parseSearch(value: string | null): string {
  return value ?? DEFAULT_FILTERS.search;
}

function parseStockCode(value: string | null): string | null {
  if (value === null) return null;
  const normalized = value.trim().toUpperCase();
  return STOCK_CODE_PATTERN.test(normalized) ? normalized : null;
}

/**
 * URL 쿼리 문자열에서 필터·선택 종목 상태를 복원합니다.
 * 파라미터가 없거나 잘못된 값이면 기본값으로 조용히 폴백합니다.
 */
export function parseAppStateFromSearch(search: string): UrlAppState {
  const params = new URLSearchParams(search);
  return {
    filters: {
      market: parseMarket(params.get(PARAM_MARKET)),
      eventTypes: parseEventTypes(params.get(PARAM_EVENT_TYPES)),
      year: parseYear(params.get(PARAM_YEAR)),
      search: parseSearch(params.get(PARAM_SEARCH))
    },
    selectedStockCode: parseStockCode(params.get(PARAM_STOCK))
  };
}

/**
 * 필터·선택 종목 상태를 URL 쿼리 문자열("?..." 또는 빈 문자열)로 직렬화합니다.
 * 기본값과 같은 항목은 URL을 깨끗하게 유지하기 위해 생략합니다.
 * selectedStockCode가 defaultStockCode와 같으면 stock 파라미터도 생략합니다.
 */
export function serializeAppState(
  filters: Filters,
  selectedStockCode: string,
  defaultStockCode = ""
): string {
  const params = new URLSearchParams();
  if (filters.market !== DEFAULT_FILTERS.market) {
    params.set(PARAM_MARKET, filters.market);
  }
  if (filters.eventTypes.length > 0) {
    params.set(PARAM_EVENT_TYPES, filters.eventTypes.join(","));
  }
  if (filters.year !== DEFAULT_FILTERS.year) {
    params.set(PARAM_YEAR, filters.year);
  }
  if (filters.search.trim().length > 0) {
    params.set(PARAM_SEARCH, filters.search);
  }
  if (selectedStockCode && selectedStockCode !== defaultStockCode) {
    params.set(PARAM_STOCK, selectedStockCode);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}
