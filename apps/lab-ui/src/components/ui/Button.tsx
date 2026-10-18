import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  children: ReactNode;
};

const variantClass: Record<ButtonVariant, string> = {
  primary:
    "bg-gradient-to-b from-accent to-accent-dim text-white shadow-glow-sm ring-1 ring-accent/40 hover:from-blue-400 hover:to-accent active:brightness-95",
  secondary:
    "border border-border-bright/60 bg-panel-elevated/80 text-slate-100 shadow-card hover:border-accent/45 hover:bg-panel-elevated",
  ghost: "text-slate-300 hover:bg-white/[0.06] hover:text-white",
};

export function Button({
  variant = "primary",
  className = "",
  children,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-1.5 rounded-xl px-4 py-2 text-sm font-medium transition duration-200 disabled:cursor-not-allowed disabled:opacity-50 ${variantClass[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
