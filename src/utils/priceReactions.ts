import type { DataQuality, PriceReaction } from "../types/buybacks";

interface DisplayReaction {
  label: string;
  value: number | null;
  quality: DataQuality;
}

export function displayRelativeReaction(reaction: PriceReaction | undefined): DisplayReaction {
  if (!reaction) {
    return { label: "\uC9C0\uC218\uB300\uBE44 +20D", value: null, quality: "missing" };
  }

  return {
    label: "\uC9C0\uC218\uB300\uBE44 +20D",
    value: isUsableNumber(reaction.abnormal_return_20d) ? reaction.abnormal_return_20d : null,
    quality: reaction.data_quality
  };
}

export function displaySimpleReaction(reaction: PriceReaction | undefined): DisplayReaction {
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

export function displayReaction(reaction: PriceReaction | undefined): DisplayReaction {
  return displayRelativeReaction(reaction);
}

export function displayReactionValue(reaction: PriceReaction | undefined): number | null {
  return displayRelativeReaction(reaction).value;
}

function isUsableNumber(value: number | null | undefined): value is number {
  return value !== null && value !== undefined && !Number.isNaN(value);
}
