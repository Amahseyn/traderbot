type StatusBadgeProps = {
  status: string;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  let className = "bg-panel-elevated text-muted border border-border";
  let dotClass = "bg-muted";

  if (normalized === "completed") {
    className = "bg-positive/10 text-positive border border-positive/25";
    dotClass = "bg-positive";
  } else if (normalized === "running" || normalized === "queued") {
    className = "bg-warning/10 text-warning border border-warning/25";
    dotClass = "bg-warning animate-pulse";
  } else if (normalized === "failed") {
    className = "bg-negative/10 text-negative border border-negative/25";
    dotClass = "bg-negative";
  } else if (normalized === "cancelled") {
    className = "bg-panel-elevated text-muted border border-border";
    dotClass = "bg-muted";
  }

  return (
    <span className={`inline-flex items-center gap-1.5 rounded px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider tabular-nums ${className}`}>
      <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${dotClass}`} aria-hidden />
      {status}
    </span>
  );
}
