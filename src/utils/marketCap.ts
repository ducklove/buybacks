import type {
  EventType,
  LatestPriceSnapshot,
  PriceReaction,
  TreasuryHoldingSnapshot
} from "../types/buybacks";

export interface MarketCapSnapshot {
  amount: number | null;
  close: number | null;
  issuedShares: number | null;
  priceDate: string | null;
}

export function marketCapFrom(
  price: LatestPriceSnapshot | PriceReaction | undefined,
  holding: TreasuryHoldingSnapshot | undefined
): MarketCapSnapshot {
  const close = closeFrom(price);
  const issuedShares = holding?.issued_shares ?? issuedSharesFrom(price);
  const providedMarketCap = marketCapAmountFrom(price);
  return {
    amount: providedMarketCap ?? (close !== null && issuedShares !== null ? close * issuedShares : null),
    close,
    issuedShares,
    priceDate: priceDateFrom(price)
  };
}

export function latestMarketCap(
  latestPrice: LatestPriceSnapshot | undefined,
  reactions: PriceReaction[],
  holding: TreasuryHoldingSnapshot | undefined
): MarketCapSnapshot {
  const latestReaction = [...reactions]
    .filter((reaction) => reaction.close_t0 !== null)
    .sort((a, b) => b.event_date.localeCompare(a.event_date))[0];
  return marketCapFrom(latestPrice ?? latestReaction, holding);
}

export function plannedAcquisitionStake(
  eventType: EventType,
  plannedAmount: number | null | undefined,
  marketCap: number | null | undefined
): number | null {
  if (!isAcquisitionPlanEvent(eventType) || plannedAmount === null || plannedAmount === undefined) {
    return null;
  }
  if (marketCap === null || marketCap === undefined || marketCap <= 0) {
    return null;
  }
  return plannedAmount / marketCap;
}

export function isAcquisitionPlanEvent(eventType: EventType) {
  return eventType === "direct_acquisition" || eventType === "trust_contract_start";
}

function closeFrom(price: LatestPriceSnapshot | PriceReaction | undefined) {
  if (!price) return null;
  if ("close" in price) return price.close;
  return price.close_t0;
}

function priceDateFrom(price: LatestPriceSnapshot | PriceReaction | undefined) {
  if (!price) return null;
  if ("price_date" in price) return price.price_date;
  return price.event_date;
}

function issuedSharesFrom(price: LatestPriceSnapshot | PriceReaction | undefined) {
  if (!price || !("issued_shares" in price)) return null;
  return positiveNumber(price.issued_shares);
}

function marketCapAmountFrom(price: LatestPriceSnapshot | PriceReaction | undefined) {
  if (!price || !("market_cap_krw" in price)) return null;
  return positiveNumber(price.market_cap_krw);
}

function positiveNumber(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? value : null;
}
