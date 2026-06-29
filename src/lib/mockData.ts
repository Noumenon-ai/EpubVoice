import type { Chapter, RenderJob, TtsParameter } from "./types";

export const defaultParameters: TtsParameter[] = [
  { name: "exaggeration", type: "number", default: 0.5, minimum: 0, maximum: 2, nullable: false },
  { name: "cfg_weight", type: "number", default: 0.5, minimum: 0, maximum: 2, nullable: false },
  { name: "pace_weight", type: "number", default: 1, minimum: 0, maximum: 2, nullable: false },
  { name: "temperature", type: "number", default: 0.8, minimum: 0, maximum: 5, nullable: false },
  { name: "seed", type: "integer", default: null, minimum: 0, maximum: 2147483647, nullable: true },
  { name: "reference_voice_path", type: "string", default: null, minimum: null, maximum: null, nullable: true }
];

export const sampleChapters: Chapter[] = [
  {
    id: "chapter-1",
    title: "Opening Room Tone",
    text: "The archive breathed softly as Mara opened the recovered volume and marked the first clean paragraph for narration.",
    reading_order: 0,
    sentences: ["The archive breathed softly as Mara opened the recovered volume and marked the first clean paragraph for narration."],
    excluded: false
  },
  {
    id: "chapter-2",
    title: "A Measured Voice",
    text: "She adjusted the pace, cooled the temperature, and listened for the point where the machine stopped performing and started reading.",
    reading_order: 1,
    sentences: ["She adjusted the pace, cooled the temperature, and listened for the point where the machine stopped performing and started reading."],
    excluded: false
  },
  {
    id: "chapter-3",
    title: "Production Notes",
    text: "Footnotes, acknowledgements, and duplicated captions waited on a separate pass so the final audiobook would move without interruption.",
    reading_order: 2,
    sentences: ["Footnotes, acknowledgements, and duplicated captions waited on a separate pass so the final audiobook would move without interruption."],
    excluded: true
  }
];

export const idleJob: RenderJob = {
  job_id: "local-preview",
  status: "idle",
  book_id: "sample-book",
  total_chapters: 0,
  completed_chapters: 0,
  current_chapter_id: null,
  output_path: null,
  error: null
};
