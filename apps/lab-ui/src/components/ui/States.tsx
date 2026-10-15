import type { ReactNode } from "react";

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-lg bg-panel ${className}`} aria-hidden />;
}

export function PageSkeleton({ tiles = 3 }: { tiles?: number }) {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-10 w-2/3 sm:w-1/2" />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        {Array.from({ length: tiles }, (_, index) => (
          <Skeleton key={index} className="h-20 rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-64 rounded-xl" />
    </div>
  );
}

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-9" />
      ))}
    </div>
  );
}

export function EmptyState({ title, description, action }: { title: string; description?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed border-border bg-panel/40 px-6 py-10 text-center">
      <p className="font-medium text-white">{title}</p>
      {description && <div className="text-muted mt-1 max-w-md text-sm">{description}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ title = "Something went wrong", error, action }: { title?: string; error?: unknown; action?: ReactNode }) {
  const message = error instanceof Error ? error.message : error ? String(error) : null;
  return (
    <div role="alert" className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm">
      <p className="font-medium text-red-300">{title}</p>
      {message && <p className="mt-1 break-words text-red-200/80">{message}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
