import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  eyebrow?: string;
  description?: string;
  actions?: ReactNode;
};

export function PageHeader({ title, eyebrow, description, actions }: PageHeaderProps) {
  return (
    <header className="flex flex-col gap-4 border-b border-border pb-5 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0 space-y-1">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1 className="text-xl font-bold tracking-tight text-white sm:text-2xl">{title}</h1>
        {description && <p className="max-w-2xl text-xs leading-relaxed text-muted sm:text-sm">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2 pt-1">{actions}</div>}
    </header>
  );
}
