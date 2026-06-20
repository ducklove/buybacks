import { validateDataset } from "./schema";
import type {
  BuybackEvent,
  BuybacksDataset,
  Company,
  DataStatus,
  PriceReaction,
  TreasuryHoldingSnapshot
} from "../types/buybacks";

const DATA_BASE = `${import.meta.env.BASE_URL}data/buybacks`;

async function fetchJson<T>(fileName: string): Promise<T> {
  const response = await fetch(`${DATA_BASE}/${fileName}`);
  if (!response.ok) {
    throw new Error(`Failed to load ${fileName}: ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function loadBuybacksDataset(): Promise<BuybacksDataset> {
  const [companies, events, holdingSnapshots, priceReactions, status] = await Promise.all([
    fetchJson<Company[]>("companies.json"),
    fetchJson<BuybackEvent[]>("events.json"),
    fetchJson<TreasuryHoldingSnapshot[]>("holding_snapshots.json"),
    fetchJson<PriceReaction[]>("price_reactions.json"),
    fetchJson<DataStatus>("data_status.json")
  ]);

  const dataset: BuybacksDataset = {
    companies,
    events,
    holdingSnapshots,
    priceReactions,
    status
  };
  const errors = validateDataset(dataset);
  if (errors.length > 0) {
    throw new Error(`Buybacks dataset validation failed:\n${errors.join("\n")}`);
  }
  return dataset;
}

