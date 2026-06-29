import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ParameterPanel } from "./ParameterPanel";
import { defaultParameters } from "../lib/mockData";
import { initialParameterValues } from "../lib/parameters";

describe("ParameterPanel", () => {
  it("binds every Chatterbox parameter with defaults and inline ranges", () => {
    const values = initialParameterValues(defaultParameters);

    render(
      <ParameterPanel
        parameters={defaultParameters}
        values={values}
        error={null}
        loading={false}
        onChange={vi.fn()}
      />
    );

    for (const parameter of defaultParameters) {
      const label = parameter.name.replaceAll("_", " ");
      expect(screen.getAllByLabelText(new RegExp(label, "i")).length).toBeGreaterThan(0);
      expect(screen.getAllByText(new RegExp(`default ${parameter.default ?? "empty"}`, "i")).length).toBeGreaterThan(0);
    }
    expect(screen.getByText(/0 to 5, default 0.8/i)).toBeInTheDocument();
  });

  it("emits coerced values from slider, number, and nullable text inputs", () => {
    const onChange = vi.fn();
    const values = initialParameterValues(defaultParameters);

    render(
      <ParameterPanel
        parameters={defaultParameters}
        values={values}
        error={null}
        loading={false}
        onChange={onChange}
      />
    );

    fireEvent.change(screen.getByLabelText(/temperature value/i), { target: { value: "1.35" } });
    fireEvent.change(screen.getByLabelText(/reference voice path/i), { target: { value: "/voices/ref.wav" } });

    expect(onChange).toHaveBeenCalledWith("temperature", 1.35);
    expect(onChange).toHaveBeenCalledWith("reference_voice_path", "/voices/ref.wav");
  });

  it("shows loading and error states accessibly", () => {
    render(
      <ParameterPanel
        parameters={defaultParameters}
        values={initialParameterValues(defaultParameters)}
        error="Unable to load parameter schema."
        loading={true}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByRole("status")).toHaveTextContent(/loading parameter schema/i);
    expect(screen.getByRole("alert")).toHaveTextContent(/unable to load/i);
  });
});
