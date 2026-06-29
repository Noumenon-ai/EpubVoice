import type { ParameterValues, TtsParameter } from "../lib/types";
import { coerceParameterValue, labelFor, rangeText } from "../lib/parameters";

interface ParameterPanelProps {
  parameters: TtsParameter[];
  values: ParameterValues;
  error: string | null;
  loading: boolean;
  onChange: (name: string, value: number | string | null) => void;
}

export function ParameterPanel({ parameters, values, error, loading, onChange }: ParameterPanelProps) {
  return (
    <section className="panel parameter-panel" aria-labelledby="parameter-heading">
      <div className="section-kicker">Chatterbox Controls</div>
      <h2 id="parameter-heading">Voice parameters</h2>
      {loading ? <p className="state-line" role="status">Loading parameter schema.</p> : null}
      {error ? <p className="error-line" role="alert">{error}</p> : null}
      <div className="parameter-grid">
        {parameters.map((parameter) => (
          <div className="field-block" key={parameter.name}>
            <label htmlFor={`parameter-${parameter.name}`}>
              <span>{labelFor(parameter.name)}</span>
              <small>{rangeText(parameter)}</small>
            </label>
            {parameter.type === "string" ? (
              <input
                id={`parameter-${parameter.name}`}
                value={String(values[parameter.name] ?? "")}
                placeholder={parameter.nullable ? "No reference voice" : ""}
                onChange={(event) => onChange(parameter.name, coerceParameterValue(parameter, event.target.value))}
              />
            ) : (
              <div className="range-row">
                <input
                  id={`parameter-${parameter.name}`}
                  type="range"
                  min={parameter.minimum ?? 0}
                  max={parameter.maximum ?? 100}
                  step={parameter.type === "integer" ? 1 : 0.05}
                  value={Number(values[parameter.name] ?? parameter.minimum ?? 0)}
                  onChange={(event) => onChange(parameter.name, coerceParameterValue(parameter, event.target.value))}
                />
                <input
                  aria-label={`${labelFor(parameter.name)} value`}
                  className="number-input"
                  type="number"
                  min={parameter.minimum ?? undefined}
                  max={parameter.maximum ?? undefined}
                  step={parameter.type === "integer" ? 1 : 0.05}
                  value={values[parameter.name] === null ? "" : String(values[parameter.name])}
                  onChange={(event) => onChange(parameter.name, coerceParameterValue(parameter, event.target.value))}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
