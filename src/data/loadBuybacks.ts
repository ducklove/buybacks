import { validateAnalysisDataset, validateDataset, validateDetailDataset } from "./schema";
import type {
  BuybackEvent,
  BuybackExecution,
  BuybacksDataset,
  CarCurves,
  Company,
  DataStatus,
  DividendRecord,
  LatestPriceSnapshot,
  PriceReaction,
  ReactionSeries,
  TreasuryHoldingSnapshot
} from "../types/buybacks";

const DATA_BASE = `${import.meta.env.BASE_URL}data/buybacks`;

function loadErrorMessage(fileName: string, status: number): string {
  if (status === 404) {
    return `${fileName} 파일을 찾을 수 없습니다 (404). 데이터셋이 아직 생성되지 않았을 수 있습니다.`;
  }
  return `${fileName} 파일을 불러오지 못했습니다 (HTTP ${status}).`;
}

async function fetchDataFile(fileName: string): Promise<Response> {
  try {
    return await fetch(`${DATA_BASE}/${fileName}`);
  } catch {
    throw new Error(`${fileName} 요청 중 네트워크 오류가 발생했습니다. 연결 상태를 확인해 주세요.`);
  }
}

async function fetchJson<T>(fileName: string): Promise<T> {
  const response = await fetchDataFile(fileName);
  if (!response.ok) {
    throw new Error(loadErrorMessage(fileName, response.status));
  }
  return (await response.json()) as T;
}

async function fetchOptionalJson<T>(fileName: string, fallback: T): Promise<T> {
  const response = await fetchDataFile(fileName);
  if (response.status === 404) {
    return fallback;
  }
  if (!response.ok) {
    throw new Error(loadErrorMessage(fileName, response.status));
  }
  // 개발 서버(SPA fallback)는 없는 파일에 404 대신 index.html 을 반환할 수 있다.
  // JSON 이 아닌 응답은 파일 부재로 간주한다.
  const contentType = response.headers?.get("content-type") ?? "";
  if (contentType.includes("text/html")) {
    return fallback;
  }
  return (await response.json()) as T;
}

/**
 * 첫 화면(KPI·차트·이벤트 테이블 뼈대) 렌더에 필요한 코어 데이터만 즉시 로드한다.
 * 대형 파일인 reaction_series/car_curves(분석 섹션)와 executions/dividends(이행·배당
 * 상세)는 loadAnalysisDataset/loadDetailDataset 으로 해당 섹션 진입 시 지연 로드한다.
 */
export async function loadBuybacksDataset(): Promise<BuybacksDataset> {
  const [companies, events, holdingSnapshots, priceReactions, latestPrices, status] =
    await Promise.all([
      fetchJson<Company[]>("companies.json"),
      fetchJson<BuybackEvent[]>("events.json"),
      fetchJson<TreasuryHoldingSnapshot[]>("holding_snapshots.json"),
      fetchJson<PriceReaction[]>("price_reactions.json"),
      fetchOptionalJson<LatestPriceSnapshot[]>("latest_prices.json", []),
      fetchJson<DataStatus>("data_status.json")
    ]);

  const dataset: BuybacksDataset = {
    companies,
    events,
    holdingSnapshots,
    priceReactions,
    latestPrices,
    executions: [],
    status
  };
  const errors = validateDataset(dataset);
  if (errors.length > 0) {
    throw new Error(`자사주 데이터셋 검증에 실패했습니다:\n${errors.join("\n")}`);
  }
  return dataset;
}

/** 분석 섹션(이벤트 스터디) 전용 지연 로드 데이터 */
export interface AnalysisDataset {
  reactionSeries: ReactionSeries[];
  carCurves: CarCurves | null;
}

/** 이행결과·배당 등 테이블/상세 화면 전용 지연 로드 데이터 */
export interface DetailDataset {
  executions: BuybackExecution[];
  dividends: DividendRecord[];
}

let analysisDatasetPromise: Promise<AnalysisDataset> | null = null;
let detailDatasetPromise: Promise<DetailDataset> | null = null;

/**
 * reaction_series/car_curves 를 지연 로드한다. 모듈 레벨 promise 캐시라 여러 번
 * 호출해도 요청은 한 번이며, 실패 시 캐시를 비워 재시도가 가능하다.
 */
export function loadAnalysisDataset(): Promise<AnalysisDataset> {
  if (!analysisDatasetPromise) {
    analysisDatasetPromise = fetchAnalysisDataset().catch((error: unknown) => {
      analysisDatasetPromise = null;
      throw error;
    });
  }
  return analysisDatasetPromise;
}

async function fetchAnalysisDataset(): Promise<AnalysisDataset> {
  const [reactionSeries, carCurves] = await Promise.all([
    fetchOptionalJson<ReactionSeries[]>("reaction_series.json", []),
    fetchOptionalJson<CarCurves | null>("car_curves.json", null)
  ]);
  const errors = validateAnalysisDataset({ reactionSeries, carCurves });
  if (errors.length > 0) {
    throw new Error(`분석 데이터셋 검증에 실패했습니다:\n${errors.join("\n")}`);
  }
  return { reactionSeries, carCurves };
}

/**
 * executions/dividends 를 지연 로드한다. knownEventIds 는 executions 의
 * linked_event_id 검증에 쓰이며, 캐시 특성상 최초 호출의 값만 사용된다.
 */
export function loadDetailDataset(knownEventIds: ReadonlySet<string>): Promise<DetailDataset> {
  if (!detailDatasetPromise) {
    detailDatasetPromise = fetchDetailDataset(knownEventIds).catch((error: unknown) => {
      detailDatasetPromise = null;
      throw error;
    });
  }
  return detailDatasetPromise;
}

async function fetchDetailDataset(knownEventIds: ReadonlySet<string>): Promise<DetailDataset> {
  const [executions, dividends] = await Promise.all([
    fetchOptionalJson<BuybackExecution[]>("executions.json", []),
    fetchOptionalJson<DividendRecord[]>("dividends.json", [])
  ]);
  const errors = validateDetailDataset({ executions, dividends }, knownEventIds);
  if (errors.length > 0) {
    throw new Error(`이행·배당 데이터셋 검증에 실패했습니다:\n${errors.join("\n")}`);
  }
  return { executions, dividends };
}

/** 테스트에서 지연 로드 promise 캐시를 초기화한다. */
export function resetBuybacksDataCache() {
  analysisDatasetPromise = null;
  detailDatasetPromise = null;
}
