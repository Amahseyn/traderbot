"use client";

import { Field, SelectInput, TextInput } from "@/components/ui/Field";
import type { StrategyParamField } from "@/lib/api";

export function prettyParamLabel(name: string): string {
  return name.replaceAll("_", " ");
}

export function defaultsFromParamFields(fields: StrategyParamField[]): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const field of fields) {
    values[field.name] = field.default;
  }
  return values;
}

function sourceHint(source: string | undefined): string | undefined {
  if (!source || source === "default") {
    return undefined;
  }
  if (source === "robust") {
    return "Robust tuned default";
  }
  if (source === "sweep") {
    return "Best optimizer sweep for this market";
  }
  return source;
}

type StrategyParamFieldsProps = {
  fields: StrategyParamField[];
  values: Record<string, unknown>;
  onChange?: (name: string, value: unknown) => void;
  sources?: Record<string, string>;
  disabled?: boolean;
};

export function StrategyParamFields({
  fields,
  values,
  onChange,
  sources,
  disabled = false,
}: StrategyParamFieldsProps) {
  if (fields.length === 0) {
    return null;
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {fields.map((field) => {
        const value = values[field.name];
        const label = prettyParamLabel(field.name);
        const hint = sourceHint(sources?.[field.name]);
        if (field.kind === "bool") {
          return (
            <label key={field.name} className="flex items-center gap-2 text-sm text-slate-200">
              <input
                type="checkbox"
                checked={value === true}
                disabled={disabled}
                onChange={(event) => onChange?.(field.name, event.target.checked)}
              />
              <span>
                {label}
                {hint && <span className="ml-1 text-xs text-muted">({hint})</span>}
              </span>
            </label>
          );
        }
        if (field.kind === "string") {
          return (
            <Field key={field.name} label={label} hint={hint}>
              <TextInput
                value={value == null ? "" : String(value)}
                disabled={disabled}
                onChange={(event) => onChange?.(field.name, event.target.value)}
              />
            </Field>
          );
        }
        return (
          <Field key={field.name} label={label} hint={hint}>
            <TextInput
              type="number"
              step={field.kind === "int" ? 1 : "any"}
              disabled={disabled}
              value={value == null || value === "" ? "" : String(value)}
              onChange={(event) =>
                onChange?.(field.name, event.target.value === "" ? null : Number(event.target.value))
              }
            />
          </Field>
        );
      })}
    </div>
  );
}
