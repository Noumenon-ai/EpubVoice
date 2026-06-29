import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RenderPanel } from "./RenderPanel";
import { idleJob } from "../lib/mockData";
import type { RenderJob } from "../lib/types";

const idlePreview = { status: "idle", url: null, message: null } as const;

function renderPanel(renderJob: RenderJob) {
  return render(
    <RenderPanel
      preview={idlePreview}
      sampleLine="A calm narration line."
      renderJob={renderJob}
      renderError={null}
      onSampleLineChange={vi.fn()}
      onPreview={vi.fn()}
      onRender={vi.fn()}
      onCancel={vi.fn()}
    />
  );
}

describe("RenderPanel", () => {
  it("enables Full render and disables Cancel in the idle pre-render state", () => {
    renderPanel(idleJob);

    expect(screen.getByRole("button", { name: /full render/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeDisabled();
  });

  it("disables Full render and enables Cancel while a render is active", () => {
    renderPanel({ ...idleJob, status: "running", total_chapters: 3, completed_chapters: 1 });

    expect(screen.getByRole("button", { name: /rendering/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /cancel/i })).toBeEnabled();
  });

  it("reports progress to assistive tech via the progressbar", () => {
    renderPanel({ ...idleJob, status: "running", total_chapters: 4, completed_chapters: 2 });

    const meter = screen.getByRole("progressbar");
    expect(meter).toHaveAttribute("aria-valuenow", "50");
    expect(meter).toHaveAttribute("aria-valuetext", "2 of 4 chapters rendered");
  });
});
