import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive";
type ButtonSize = "xs" | "sm" | "md";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
};

const variantClass: Record<ButtonVariant, string> = {
  primary:
    "bg-accent text-on-accent font-medium hover:bg-accent/90 active:bg-accent-dim shadow-sm",
  secondary:
    "border border-border bg-panel text-zinc-200 hover:border-border-bright hover:bg-panel-elevated active:bg-panel",
  ghost: "text-zinc-400 hover:bg-panel-elevated hover:text-white",
  destructive:
    "bg-red-600 text-white font-medium hover:bg-red-500 active:bg-red-700 shadow-sm",
};

const sizeClass: Record<ButtonSize, string> = {
  xs: "px-2 py-1 text-xs",
  sm: "px-2.5 py-1 text-xs sm:text-xs",
  md: "px-3 py-1.5 text-xs sm:text-sm",
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  children,
  type = "button",
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface disabled:pointer-events-none disabled:opacity-50 select-none ${sizeClass[size]} ${variantClass[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
