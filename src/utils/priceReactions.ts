import type { DataQuality, PriceReaction } from "../types/buybacks";

interface DisplayReaction {
  label: string;
  value: number | null;
  quality: DataQuality;
}

export function displayReaction(reaction: PriceReaction | undefined): DisplayReaction {
  if (!reaction) {
    return { label: "+20D", value: null, quality: "missing" };
  }

  const candidates: Array<{ label: string; value: number | null }> = [
    { label: "+20D", value: reaction.return_20d },
    { label: "+5D", value: reaction.return_5d },
    { label: "+1D", value: reaction.return_1d }
  ];
  const available = candidates.find(
    (candidate) =>
      candidate.value !== null &&
      candidate.value !== undefined &&
      !Number.isNaN(candidate.value)
  );
  if (available) {
    return { ...available, quality: reaction.data_quality };
  }
  return {
    label: reaction.close_t0 === null ? "+20D" : "T+0",
    value: null,
    quality: reaction.data_quality
  };
}

export function displayReactionValue(reaction: PriceReaction | undefined): number | null {
  return displayReaction(reaction).value;
}
