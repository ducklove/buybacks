/** 원화 1억 (100,000,000원) */
export const KRW_EOK = 1_0000_0000;

/** 원화 1조 (1,000,000,000,000원) */
export const KRW_JO = 1_0000_0000_0000;

/** 이벤트 테이블 페이지 크기 옵션 */
export const TABLE_PAGE_SIZE_OPTIONS = [25, 50, 100] as const;

export type TablePageSize = (typeof TABLE_PAGE_SIZE_OPTIONS)[number];

/** 이벤트 테이블 기본 페이지 크기 */
export const DEFAULT_TABLE_PAGE_SIZE: TablePageSize = 25;

/** 페이지네이션에 동시에 노출할 페이지 번호 버튼 수 */
export const PAGINATION_WINDOW_SIZE = 5;

/** KPI 집계 시 "최근"으로 간주하는 기간(개월) */
export const KPI_LOOKBACK_MONTHS = 12;
