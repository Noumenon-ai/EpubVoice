import { describe, expect, it } from "vitest";
import {
  estimateDurationSeconds,
  includedTotals,
  mergeAdjacentChapters,
  splitChapter,
  splitOffsetForRatio,
  toggleChapterExcluded,
  wordCount
} from "./chapterLogic";
import { sampleChapters } from "./mockData";

describe("chapter split logic", () => {
  it("calculates live word and duration estimates for included chapters", () => {
    expect(wordCount("One two  three.")).toBe(3);
    expect(estimateDurationSeconds("One two three")).toBeGreaterThan(0);

    const totals = includedTotals(sampleChapters);

    expect(totals.count).toBe(2);
    expect(totals.words).toBe(38);
    expect(totals.seconds).toBeGreaterThan(0);
  });

  it("splits at a clamped word boundary and renumbers chapters", () => {
    const split = splitChapter(sampleChapters, "chapter-1", 0.5);

    expect(split).toHaveLength(4);
    expect(split[0].id).toBe("chapter-1");
    expect(split[1].id).toBe("chapter-1-part-2");
    expect(split.map((chapter) => chapter.reading_order)).toEqual([0, 1, 2, 3]);
    expect(split[0].text.split(/\s+/).length).toBeGreaterThan(1);
    expect(split[1].text.split(/\s+/).length).toBeGreaterThan(1);
  });

  it("rejects chapters that cannot leave text on both sides", () => {
    expect(() => splitOffsetForRatio("single", 0.5)).toThrow(/at least two words/i);
  });

  it("merges only adjacent chapters and preserves exclusion safety", () => {
    const merged = mergeAdjacentChapters(sampleChapters, "chapter-1");

    expect(merged).toHaveLength(2);
    expect(merged[0].title).toContain("Opening Room Tone / A Measured Voice");
    expect(merged[0].excluded).toBe(false);
    expect(merged.map((chapter) => chapter.reading_order)).toEqual([0, 1]);
  });

  it("toggles exclusions without mutating the original chapter list", () => {
    const updated = toggleChapterExcluded(sampleChapters, "chapter-1");

    expect(updated[0].excluded).toBe(true);
    expect(sampleChapters[0].excluded).toBe(false);
  });
});
