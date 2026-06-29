import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

function setPath(pathname: string) {
  window.history.replaceState({}, "", pathname);
}

describe("App routing", () => {
  afterEach(() => {
    setPath("/");
    vi.restoreAllMocks();
  });

  it("renders the 404 view for unknown paths without mounting the studio", () => {
    setPath("/missing-reel");

    render(<App />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/not in this session/i);
    expect(screen.queryByText(/voice parameters/i)).not.toBeInTheDocument();
  });

  it("mounts the studio shell on the root path", () => {
    setPath("/");
    // Studio fetches the parameter schema on mount; stub it so the test is hermetic.
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new Error("offline")))
    );

    render(<App />);

    expect(screen.getByRole("heading", { name: /read the book like a mastering session/i })).toBeInTheDocument();
    expect(screen.getByText(/voice parameters/i)).toBeInTheDocument();
  });
});
