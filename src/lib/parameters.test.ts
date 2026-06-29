import { describe, expect, it } from "vitest";
import { coerceParameterValue, initialParameterValues, labelFor, rangeText } from "./parameters";
import { defaultParameters } from "./mockData";
import type { TtsParameter } from "./types";

const temperature = defaultParameters.find((p) => p.name === "temperature") as TtsParameter;
const seed = defaultParameters.find((p) => p.name === "seed") as TtsParameter;
const reference = defaultParameters.find((p) => p.name === "reference_voice_path") as TtsParameter;

describe("parameter binding", () => {
  it("seeds initial values from each parameter default", () => {
    const values = initialParameterValues(defaultParameters);
    expect(values.temperature).toBe(0.8);
    expect(values.seed).toBeNull();
    expect(values.reference_voice_path).toBeNull();
  });

  it("clamps numbers to the parameter range and rounds floats", () => {
    expect(coerceParameterValue(temperature, "9.9")).toBe(5);
    expect(coerceParameterValue(temperature, "-3")).toBe(0);
    expect(coerceParameterValue(temperature, "1.23456")).toBe(1.235);
  });

  it("truncates and clamps integer parameters", () => {
    expect(coerceParameterValue(seed, "42.9")).toBe(42);
    expect(coerceParameterValue(seed, "-1")).toBe(0);
  });

  it("treats empty input as null for nullable fields", () => {
    expect(coerceParameterValue(seed, "")).toBeNull();
    expect(coerceParameterValue(reference, "   ")).toBeNull();
  });

  it("rejects non-numeric input for numeric parameters", () => {
    expect(() => coerceParameterValue(temperature, "loud")).toThrow(/must be a number/i);
    expect(() => coerceParameterValue(seed, "abc")).toThrow(/must be an integer/i);
  });

  it("renders human labels and inline range hints", () => {
    expect(labelFor("reference_voice_path")).toBe("Reference Voice Path");
    expect(rangeText(temperature)).toBe("0 to 5, default 0.8");
    expect(rangeText(seed)).toBe("0 to 2147483647, default empty");
  });
});
