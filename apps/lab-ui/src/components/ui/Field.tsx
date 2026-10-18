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
  "w-full rounded-xl border border-border/80 bg-surface/90 px-3.5 py-2.5 text-sm text-slate-100 shadow-inner shadow-black/10 placeholder:text-muted transition duration-150 focus:border-accent/60 focus:bg-surface focus:outline-none focus:ring-2 focus:ring-accent/25";

export function TextInput({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={className ? `${inputClass} ${className}` : inputClass} {...props} />;
}

export function SelectInput({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={className ? `${inputClass} ${className}` : inputClass} {...props} />;
}
