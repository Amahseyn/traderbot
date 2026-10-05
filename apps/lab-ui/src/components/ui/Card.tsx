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
    <section className={`rounded-xl border border-border bg-panel p-5 shadow-sm ${className}`}>
      {(title || description || actions) && (
        <header className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            {title && <h2 className="text-base font-semibold text-white">{title}</h2>}
            {description && <p className="text-muted mt-1 text-sm">{description}</p>}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}
