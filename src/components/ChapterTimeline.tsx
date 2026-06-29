import type { Chapter } from "../lib/types";
import {
  estimateDurationSeconds,
  formatDuration,
  includedTotals,
  mergeAdjacentChapters,
  splitChapter,
  toggleChapterExcluded,
  wordCount
} from "../lib/chapterLogic";

interface ChapterTimelineProps {
  chapters: Chapter[];
  splitRatio: number;
  error: string | null;
  onChaptersChange: (chapters: Chapter[]) => void;
  onSplitRatioChange: (ratio: number) => void;
  onError: (message: string | null) => void;
}

export function ChapterTimeline({
  chapters,
  splitRatio,
  error,
  onChaptersChange,
  onSplitRatioChange,
  onError
}: ChapterTimelineProps) {
  const totals = includedTotals(chapters);

  function applySplit(chapterId: string) {
    try {
      onChaptersChange(splitChapter(chapters, chapterId, splitRatio));
      onError(null);
    } catch (splitError) {
      onError(splitError instanceof Error ? splitError.message : "Unable to split chapter.");
    }
  }

  function applyMerge(chapterId: string) {
    try {
      onChaptersChange(mergeAdjacentChapters(chapters, chapterId));
      onError(null);
    } catch (mergeError) {
      onError(mergeError instanceof Error ? mergeError.message : "Unable to merge chapters.");
    }
  }

  return (
    <section className="panel chapter-panel" aria-labelledby="chapter-heading">
      <div className="chapter-heading-row">
        <div>
          <div className="section-kicker">Chapter Assembly</div>
          <h2 id="chapter-heading">Split, merge, exclude</h2>
        </div>
        <div className="totals-strip" aria-label="Included chapter totals">
          <strong>{totals.count}</strong> included
          <span>{totals.words} words</span>
          <span>{formatDuration(totals.seconds)}</span>
        </div>
      </div>
      <label className="split-control" htmlFor="split-ratio">
        <span>Drag split point</span>
        <input
          id="split-ratio"
          type="range"
          min="10"
          max="90"
          value={Math.round(splitRatio * 100)}
          onChange={(event) => onSplitRatioChange(Number(event.target.value) / 100)}
        />
        <b>{Math.round(splitRatio * 100)}%</b>
      </label>
      {error ? <p className="error-line" role="alert">{error}</p> : null}
      {chapters.length === 0 ? (
        <div className="empty-state">
          <h3>No chapters loaded</h3>
          <p>Upload an EPUB through the API, then return here to shape the audiobook timeline.</p>
        </div>
      ) : (
        <div className="timeline" aria-label="Chapter timeline">
          {chapters.map((chapter, index) => (
            <article className={chapter.excluded ? "chapter-card is-excluded" : "chapter-card"} key={chapter.id}>
              <div className="chapter-index">{String(index + 1).padStart(2, "0")}</div>
              <div className="chapter-body">
                <h3>{chapter.title}</h3>
                <p>{chapter.text}</p>
                <dl>
                  <div>
                    <dt>Words</dt>
                    <dd>{wordCount(chapter.text)}</dd>
                  </div>
                  <div>
                    <dt>Estimate</dt>
                    <dd>{formatDuration(estimateDurationSeconds(chapter.text))}</dd>
                  </div>
                </dl>
              </div>
              <div className="chapter-actions" aria-label={`${chapter.title} actions`}>
                <button type="button" onClick={() => applySplit(chapter.id)}>Split</button>
                <button type="button" disabled={index === chapters.length - 1} onClick={() => applyMerge(chapter.id)}>
                  Merge
                </button>
                <button type="button" onClick={() => onChaptersChange(toggleChapterExcluded(chapters, chapter.id))}>
                  {chapter.excluded ? "Include" : "Exclude"}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
