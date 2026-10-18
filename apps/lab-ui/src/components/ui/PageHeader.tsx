import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  eyebrow?: string;
  description?: string;
  actions?: ReactNode;
};

export function PageHeader({ title, eyebrow, description, actions }: PageHeaderProps) {
  return (
    <header className="relative flex flex-col gap-5 pb-8 sm:flex-row sm:items-start sm:justify-between">
      <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-border to-transparent" aria-hidden />
      <div className="min-w-0 space-y-2">
        {eyebrow && <p className="eyebrow-pill">{eyebrow}</p>}
        <h1 className="text-3xl font-semibold tracking-tight text-gradient sm:text-4xl">{title}</h1>
        {description && <p className="max-w-2xl text-base leading-relaxed text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2 pt-1">{actions}</div>}
    </header>
  );
}
