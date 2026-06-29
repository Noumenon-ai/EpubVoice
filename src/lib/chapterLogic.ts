import type { Chapter } from "./types";

export const WORDS_PER_MINUTE = 165;

export function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

export function estimateDurationSeconds(text: string): number {
  return Math.max(1, Math.round((wordCount(text) / WORDS_PER_MINUTE) * 60));
}

export function formatDuration(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return `${minutes}:${remaining.toString().padStart(2, "0")}`;
}

export function clampSplitRatio(ratio: number): number {
  if (!Number.isFinite(ratio)) {
    return 0.5;
  }
  return Math.min(0.9, Math.max(0.1, ratio));
}

export function splitOffsetForRatio(text: string, ratio: number): number {
  const normalizedRatio = clampSplitRatio(ratio);
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length < 2) {
    throw new Error("Chapter must contain at least two words to split.");
  }
  const splitAt = Math.min(words.length - 1, Math.max(1, Math.round(words.length * normalizedRatio)));
  return words.slice(0, splitAt).join(" ").length;
}

export function splitChapter(chapters: Chapter[], chapterId: string, ratio: number): Chapter[] {
  const index = chapters.findIndex((chapter) => chapter.id === chapterId);
  if (index < 0) {
    throw new Error("Chapter not found.");
  }
  const chapter = chapters[index];
  const offset = splitOffsetForRatio(chapter.text, ratio);
  const leftText = chapter.text.slice(0, offset).trim();
  const rightText = chapter.text.slice(offset).trim();
  if (!leftText || !rightText) {
    throw new Error("Split must leave text on both sides.");
  }
  const left: Chapter = {
    ...chapter,
    text: leftText,
    sentences: [leftText]
  };
  const right: Chapter = {
    ...chapter,
    id: nextSplitId(chapters, chapter.id),
    title: `${chapter.title} Part 2`,
    text: rightText,
    sentences: [rightText],
    reading_order: chapter.reading_order + 1
  };
  return renumber([...chapters.slice(0, index), left, right, ...chapters.slice(index + 1)]);
}

export function mergeAdjacentChapters(chapters: Chapter[], firstId: string): Chapter[] {
  const index = chapters.findIndex((chapter) => chapter.id === firstId);
  if (index < 0 || index >= chapters.length - 1) {
    throw new Error("Select a chapter with a following neighbor to merge.");
  }
  const first = chapters[index];
  const second = chapters[index + 1];
  const mergedText = `${first.text.trim()}\n\n${second.text.trim()}`.trim();
  const merged: Chapter = {
    ...first,
    title: `${first.title} / ${second.title}`,
    text: mergedText,
    sentences: [mergedText],
    excluded: first.excluded && second.excluded
  };
  return renumber([...chapters.slice(0, index), merged, ...chapters.slice(index + 2)]);
}

export function toggleChapterExcluded(chapters: Chapter[], chapterId: string): Chapter[] {
  return chapters.map((chapter) => (
    chapter.id === chapterId ? { ...chapter, excluded: !chapter.excluded } : chapter
  ));
}

export function includedTotals(chapters: Chapter[]): { words: number; seconds: number; count: number } {
  return chapters.reduce(
    (total, chapter) => {
      if (chapter.excluded) {
        return total;
      }
      return {
        words: total.words + wordCount(chapter.text),
        seconds: total.seconds + estimateDurationSeconds(chapter.text),
        count: total.count + 1
      };
    },
    { words: 0, seconds: 0, count: 0 }
  );
}

function nextSplitId(chapters: Chapter[], baseId: string): string {
  const existing = new Set(chapters.map((chapter) => chapter.id));
  let suffix = 2;
  while (existing.has(`${baseId}-part-${suffix}`)) {
    suffix += 1;
  }
  return `${baseId}-part-${suffix}`;
}

function renumber(chapters: Chapter[]): Chapter[] {
  return chapters.map((chapter, index) => ({ ...chapter, reading_order: index }));
}
