import { useEffect, useMemo, useRef, useState } from "react";
import { ChapterTimeline } from "./components/ChapterTimeline";
import { NotFound } from "./components/NotFound";
import { ParameterPanel } from "./components/ParameterPanel";
import { RenderPanel } from "./components/RenderPanel";
import { idleJob, sampleChapters, defaultParameters } from "./lib/mockData";
import { includedTotals } from "./lib/chapterLogic";
import { initialParameterValues } from "./lib/parameters";
import type { Chapter, ParameterValues, PreviewState, RenderJob, TtsParameter } from "./lib/types";
import heroImage from "./assets/mastering-desk.png";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

export function App() {
  // Routing decision must stay above the hooks in Studio so App itself stays
  // hook-free; an early return placed among hooks would call them conditionally
  // and violate the Rules of Hooks.
  if (typeof window !== "undefined" && window.location.pathname !== "/") {
    return <NotFound />;
  }
  return <Studio />;
}

function Studio() {
  const [parameters, setParameters] = useState<TtsParameter[]>(defaultParameters);
  const [parameterValues, setParameterValues] = useState<ParameterValues>(() => initialParameterValues(defaultParameters));
  const [parameterError, setParameterError] = useState<string | null>(null);
  const [parametersLoading, setParametersLoading] = useState(true);
  const [chapters, setChapters] = useState<Chapter[]>(sampleChapters);
  const [splitRatio, setSplitRatio] = useState(0.5);
  const [chapterError, setChapterError] = useState<string | null>(null);
  const [sampleLine, setSampleLine] = useState("A short passage, prepared for a calm and articulate audiobook voice.");
  const [preview, setPreview] = useState<PreviewState>({ status: "idle", url: null, message: null });
  const [renderJob, setRenderJob] = useState<RenderJob>(idleJob);
  const [renderError, setRenderError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);
  const totals = useMemo(() => includedTotals(chapters), [chapters]);

  useEffect(() => {
    let mounted = true;
    async function loadParameters() {
      try {
        const response = await fetch(`${API_BASE}/tts/parameters`);
        if (!response.ok) {
          throw new Error(`Parameter schema request failed with ${response.status}.`);
        }
        const loaded = await response.json() as TtsParameter[];
        if (mounted && loaded.length > 0) {
          setParameters(loaded);
          setParameterValues(initialParameterValues(loaded));
          setParameterError(null);
        }
      } catch (error) {
        if (mounted) {
          setParameterError(error instanceof Error ? error.message : "Unable to load parameter schema.");
        }
      } finally {
        if (mounted) {
          setParametersLoading(false);
        }
      }
    }
    loadParameters();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => () => {
    if (preview.url) {
      URL.revokeObjectURL(preview.url);
    }
  }, [preview.url]);

  useEffect(() => () => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
    }
  }, []);

  function updateParameter(name: string, value: number | string | null) {
    setParameterValues((current) => ({ ...current, [name]: value }));
  }

  async function requestPreview() {
    setPreview((current) => ({ ...current, status: "loading", message: "Generating preview audio." }));
    try {
      const response = await fetch(`${API_BASE}/tts/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sample_line: sampleLine, options: parameterValues })
      });
      if (!response.ok) {
        throw new Error(`Preview failed with ${response.status}.`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      setPreview((current) => {
        if (current.url) {
          URL.revokeObjectURL(current.url);
        }
        return { status: "ready", url, message: "Preview ready." };
      });
    } catch (error) {
      setPreview({
        status: "error",
        url: null,
        message: error instanceof Error ? error.message : "Preview failed."
      });
    }
  }

  async function requestRender() {
    setRenderError(null);
    if (totals.count === 0) {
      setRenderError("At least one chapter must be included before rendering.");
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/render-jobs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          book_id: renderJob.book_id,
          output_name: "studio-render",
          options: parameterValues
        })
      });
      if (!response.ok) {
        throw new Error(`Render request failed with ${response.status}.`);
      }
      const job = await response.json() as RenderJob;
      setRenderJob(job);
      startPolling(job.job_id);
    } catch (error) {
      setRenderError(error instanceof Error ? error.message : "Render request failed.");
    }
  }

  async function cancelRender() {
    if (!renderJob.job_id) {
      return;
    }
    try {
      const response = await fetch(`${API_BASE}/render-jobs/${renderJob.job_id}/cancel`, { method: "POST" });
      if (!response.ok) {
        throw new Error(`Cancel failed with ${response.status}.`);
      }
      setRenderJob(await response.json() as RenderJob);
    } catch (error) {
      setRenderError(error instanceof Error ? error.message : "Cancel request failed.");
    }
  }

  function startPolling(jobId: string) {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
    }
    pollRef.current = window.setInterval(async () => {
      try {
        const response = await fetch(`${API_BASE}/render-jobs/${jobId}`);
        if (!response.ok) {
          throw new Error(`Progress request failed with ${response.status}.`);
        }
        const job = await response.json() as RenderJob;
        setRenderJob(job);
        if (["completed", "failed", "cancelled"].includes(job.status) && pollRef.current !== null) {
          window.clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch (error) {
        setRenderError(error instanceof Error ? error.message : "Unable to poll render progress.");
        if (pollRef.current !== null) {
          window.clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }
    }, 1200);
  }

  return (
    <main className="studio-shell">
      <section className="hero-band" style={{ backgroundImage: `url(${heroImage})` }}>
        <div className="hero-copy">
          <p>EPUB Chapters Studio</p>
          <h1>Read the book like a mastering session.</h1>
        </div>
        <div className="hero-meter" aria-label="Current session estimate">
          <span>{totals.count} chapters</span>
          <strong>{totals.words} words queued</strong>
        </div>
      </section>
      <div className="workspace-grid">
        <ParameterPanel
          parameters={parameters}
          values={parameterValues}
          error={parameterError}
          loading={parametersLoading}
          onChange={updateParameter}
        />
        <RenderPanel
          preview={preview}
          sampleLine={sampleLine}
          renderJob={renderJob}
          renderError={renderError}
          onSampleLineChange={setSampleLine}
          onPreview={requestPreview}
          onRender={requestRender}
          onCancel={cancelRender}
        />
        <ChapterTimeline
          chapters={chapters}
          splitRatio={splitRatio}
          error={chapterError}
          onChaptersChange={setChapters}
          onSplitRatioChange={setSplitRatio}
          onError={setChapterError}
        />
      </div>
    </main>
  );
}
