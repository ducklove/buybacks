import { validateDataset } from "./schema";
import type {
  BuybackEvent,
  BuybackExecution,
  BuybacksDataset,
  Company,
  DataStatus,
  LatestPriceSnapshot,
  PriceReaction,
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
  return (await response.json()) as T;
}

export async function loadBuybacksDataset(): Promise<BuybacksDataset> {
  const [companies, events, holdingSnapshots, priceReactions, latestPrices, executions, status] =
    await Promise.all([
      fetchJson<Company[]>("companies.json"),
      fetchJson<BuybackEvent[]>("events.json"),
      fetchJson<TreasuryHoldingSnapshot[]>("holding_snapshots.json"),
      fetchJson<PriceReaction[]>("price_reactions.json"),
      fetchOptionalJson<LatestPriceSnapshot[]>("latest_prices.json", []),
      fetchOptionalJson<BuybackExecution[]>("executions.json", []),
      fetchJson<DataStatus>("data_status.json")
    ]);

  const dataset: BuybacksDataset = {
    companies,
    events,
    holdingSnapshots,
    priceReactions,
    latestPrices,
    executions,
    status
  };
  const errors = validateDataset(dataset);
  if (errors.length > 0) {
    throw new Error(`자사주 데이터셋 검증에 실패했습니다:\n${errors.join("\n")}`);
  }
  return dataset;
}
