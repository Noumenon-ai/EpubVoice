import type { ParameterValues, TtsParameter } from "./types";

export function initialParameterValues(parameters: TtsParameter[]): ParameterValues {
  return parameters.reduce<ParameterValues>((values, parameter) => {
    values[parameter.name] = parameter.default;
    return values;
  }, {});
}

export function coerceParameterValue(parameter: TtsParameter, rawValue: string): number | string | null {
  if (rawValue.trim() === "") {
    return null;
  }
  if (parameter.type === "integer") {
    const parsed = Number.parseInt(rawValue, 10);
    if (!Number.isFinite(parsed)) {
      throw new Error(`${labelFor(parameter.name)} must be an integer.`);
    }
    return clampNumber(parsed, parameter);
  }
  if (parameter.type === "number") {
    const parsed = Number.parseFloat(rawValue);
    if (!Number.isFinite(parsed)) {
      throw new Error(`${labelFor(parameter.name)} must be a number.`);
    }
    return clampNumber(parsed, parameter);
  }
  return rawValue.trim() || null;
}

export function labelFor(name: string): string {
  return name.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function rangeText(parameter: TtsParameter): string {
  const parts = [];
  if (parameter.minimum !== null || parameter.maximum !== null) {
    parts.push(`${parameter.minimum ?? "Any"} to ${parameter.maximum ?? "Any"}`);
  }
  parts.push(`default ${parameter.default ?? "empty"}`);
  return parts.join(", ");
}

function clampNumber(value: number, parameter: TtsParameter): number {
  let clamped = value;
  if (parameter.minimum !== null) {
    clamped = Math.max(parameter.minimum, clamped);
  }
  if (parameter.maximum !== null) {
    clamped = Math.min(parameter.maximum, clamped);
  }
  return parameter.type === "integer" ? Math.trunc(clamped) : Number(clamped.toFixed(3));
}
