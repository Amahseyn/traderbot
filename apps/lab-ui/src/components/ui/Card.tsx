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
      className={`relative rounded-lg border border-border bg-panel p-4 sm:p-5 ${className}`}
    >
      {(title || description || actions) && (
        <header className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-0.5">
            {title && <h2 className="text-sm font-semibold tracking-tight text-white sm:text-base">{title}</h2>}
            {description && <p className="text-xs leading-relaxed text-muted">{description}</p>}
          </div>
          {actions && <div className="shrink-0">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}
