import type { ReactNode } from "react";

type CardProps = {
  title?: ReactNode;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function Card({ title, description, actions, children, className = "" }: CardProps) {
  return (
    <section
      className={`relative overflow-hidden rounded-2xl border border-border/80 bg-gradient-to-b from-panel-elevated/90 to-panel/75 p-5 shadow-card sm:p-6 ${className}`}
    >
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/10 to-transparent"
        aria-hidden
      />
      {(title || description || actions) && (
        <header className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            {title && <h2 className="text-base font-semibold tracking-tight text-white sm:text-lg">{title}</h2>}
            {description && <p className="text-sm leading-relaxed text-muted">{description}</p>}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}
