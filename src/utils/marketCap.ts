import type { PriceReaction, TreasuryHoldingSnapshot } from "../types/buybacks";

export interface MarketCapSnapshot {
  amount: number | null;
  close: number | null;
  issuedShares: number | null;
  priceDate: string | null;
}

export function marketCapFrom(
  reaction: PriceReaction | undefined,
  holding: TreasuryHoldingSnapshot | undefined
): MarketCapSnapshot {
  const close = reaction?.close_t0 ?? null;
  const issuedShares = holding?.issued_shares ?? null;
  return {
    amount: close !== null && issuedShares !== null ? close * issuedShares : null,
    close,
    issuedShares,
    priceDate: reaction?.event_date ?? null
  };
}

export function latestMarketCap(
  reactions: PriceReaction[],
  holding: TreasuryHoldingSnapshot | undefined
): MarketCapSnapshot {
  const latestReaction = [...reactions]
    .filter((reaction) => reaction.close_t0 !== null)
    .sort((a, b) => b.event_date.localeCompare(a.event_date))[0];
  return marketCapFrom(latestReaction, holding);
}
