import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

type FieldProps = {
  label: string;
  hint?: string;
  children: ReactNode;
};

export function Field({ label, hint, children }: FieldProps) {
  return (
    <label className="block space-y-1.5 text-sm">
      <span className="font-medium text-slate-200">{label}</span>
      {children}
      {hint && <span className="block text-xs leading-relaxed text-muted">{hint}</span>}
    </label>
  );
}

const inputClass =
  "w-full rounded-lg border border-border bg-panel px-3.5 py-2 text-sm text-slate-100 placeholder:text-muted/60 transition-colors duration-150 focus:border-border-bright focus:outline-none focus:ring-1 focus:ring-accent";

export function TextInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={className ? `${inputClass} ${className}` : inputClass} {...props} />;
}

export function SelectInput({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={className ? `${inputClass} ${className}` : inputClass} {...props} />;
}
