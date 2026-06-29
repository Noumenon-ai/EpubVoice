import type { PreviewState, RenderJob } from "../lib/types";
import { formatDuration } from "../lib/chapterLogic";

interface RenderPanelProps {
  preview: PreviewState;
  sampleLine: string;
  renderJob: RenderJob;
  renderError: string | null;
  onSampleLineChange: (line: string) => void;
  onPreview: () => void;
  onRender: () => void;
  onCancel: () => void;
}

export function RenderPanel({
  preview,
  sampleLine,
  renderJob,
  renderError,
  onSampleLineChange,
  onPreview,
  onRender,
  onCancel
}: RenderPanelProps) {
  const progress = renderJob.total_chapters === 0
    ? 0
    : Math.round((renderJob.completed_chapters / renderJob.total_chapters) * 100);
  const activeRender = renderJob.status === "queued" || renderJob.status === "running";

  return (
    <section className="panel render-panel" aria-labelledby="render-heading">
      <div className="section-kicker">Output Pass</div>
      <h2 id="render-heading">Preview and render</h2>
      <label className="sample-field" htmlFor="sample-line">
        <span>Voice preview line</span>
        <textarea
          id="sample-line"
          value={sampleLine}
          maxLength={500}
          onChange={(event) => onSampleLineChange(event.target.value)}
        />
      </label>
      <div className="button-row">
        <button type="button" onClick={onPreview} disabled={preview.status === "loading"}>
          {preview.status === "loading" ? "Preparing" : "Preview voice"}
        </button>
        <button type="button" className="primary-action" onClick={onRender} disabled={activeRender}>
          {activeRender ? "Rendering" : "Full render"}
        </button>
        <button type="button" onClick={onCancel} disabled={!activeRender}>Cancel</button>
      </div>
      {preview.message ? <p className={preview.status === "error" ? "error-line" : "state-line"}>{preview.message}</p> : null}
      {preview.url ? <audio controls src={preview.url} aria-label="Voice preview player" /> : null}
      {renderError ? <p className="error-line" role="alert">{renderError}</p> : null}
      <div className="progress-block" aria-label="Render progress">
        <div className="progress-copy">
          <strong>{renderJob.status}</strong>
          <span>{renderJob.completed_chapters} of {renderJob.total_chapters} chapters</span>
          <span>{formatDuration(renderJob.completed_chapters * 90)} rendered estimate</span>
        </div>
        <div
          className="meter"
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuetext={`${renderJob.completed_chapters} of ${renderJob.total_chapters} chapters rendered`}
        >
          <span style={{ width: `${progress}%` }} />
        </div>
      </div>
    </section>
  );
}
