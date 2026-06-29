export type ParameterKind = "number" | "integer" | "string";

export interface TtsParameter {
  name: string;
  type: ParameterKind;
  default: number | string | null;
  minimum: number | null;
  maximum: number | null;
  nullable: boolean;
}

export type ParameterValues = Record<string, number | string | null>;

export interface Chapter {
  id: string;
  title: string;
  text: string;
  reading_order: number;
  sentences: string[];
  excluded: boolean;
}

// "idle" is a client-only sentinel for the pre-render state. The API never
// returns it; it keeps the initial job from being treated as an active render
// (which would disable the "Full render" button and enable "Cancel" on load).
export type RenderStatus = "idle" | "queued" | "running" | "completed" | "failed" | "cancelled";

export interface RenderJob {
  job_id: string;
  status: RenderStatus;
  book_id: string;
  total_chapters: number;
  completed_chapters: number;
  current_chapter_id: string | null;
  output_path: string | null;
  error: string | null;
}

export interface PreviewState {
  status: "idle" | "loading" | "ready" | "error";
  url: string | null;
  message: string | null;
}
