import type { DataQuality, PriceReaction } from "../types/buybacks";

export type ReturnWindow = 5 | 20 | 60;

interface DisplayReaction {
  label: string;
  value: number | null;
  quality: DataQuality;
}

export function displayRelativeReaction(
  reaction: PriceReaction | undefined,
  window: ReturnWindow = 20
): DisplayReaction {
  if (!reaction) {
    return { label: `지수대비 +${window}D`, value: null, quality: "missing" };
  }

  return {
    label: `지수대비 +${window}D`,
    value: relativeReturn(reaction, window),
    quality: reaction.data_quality
  };
}

export function displaySimpleReaction(
  reaction: PriceReaction | undefined,
  window: ReturnWindow = 20
): DisplayReaction {
  if (!reaction) {
    return { label: `+${window}D`, value: null, quality: "missing" };
  }

  const fallbackWindows = ([20, 5, 60] satisfies ReturnWindow[]).filter((item) => item !== window);
  const candidates: Array<{ label: string; value: number | null }> = [
    { label: `+${window}D`, value: simpleReturn(reaction, window) },
    ...fallbackWindows.map((item) => ({ label: `+${item}D`, value: simpleReturn(reaction, item) })),
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
    label: reaction.close_t0 === null ? `+${window}D` : "T+0",
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

export function relativeReturn(reaction: PriceReaction, window: ReturnWindow): number | null {
  const value =
    window === 5
      ? reaction.abnormal_return_5d
      : window === 60
        ? reaction.abnormal_return_60d
        : reaction.abnormal_return_20d;
  return isUsableNumber(value) ? value : null;
}

export function simpleReturn(reaction: PriceReaction, window: ReturnWindow): number | null {
  const value =
    window === 5 ? reaction.return_5d : window === 60 ? reaction.return_60d : reaction.return_20d;
  return isUsableNumber(value) ? value : null;
}

function isUsableNumber(value: number | null | undefined): value is number {
  return value !== null && value !== undefined && !Number.isNaN(value);
}
