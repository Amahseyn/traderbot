import type { ReactNode } from "react";

type CardProps = {
  title?: ReactNode;
  description?: string;
  children: ReactNode;
  className?: string;
};

export function Card({ title, description, children, className = "" }: CardProps) {
  return (
    <section className={`rounded-xl border border-border bg-panel p-5 shadow-sm ${className}`}>
      {(title || description) && (
        <header className="mb-4">
          {title && <h2 className="text-base font-semibold text-white">{title}</h2>}
          {description && <p className="text-muted mt-1 text-sm">{description}</p>}
        </header>
      )}
      {children}
    </section>
  );
}
