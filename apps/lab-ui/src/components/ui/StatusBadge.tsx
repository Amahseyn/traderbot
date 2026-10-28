type StatusBadgeProps = {
  status: string;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  let className = "bg-zinc-500/10 text-zinc-400 border border-zinc-500/25";
  let dotClass = "bg-zinc-400";

  if (normalized === "completed") {
    className = "bg-emerald-500/10 text-emerald-400 border border-emerald-500/25";
    dotClass = "bg-emerald-400";
  } else if (normalized === "running" || normalized === "queued") {
    className = "bg-amber-500/10 text-amber-400 border border-amber-500/25";
    dotClass = "bg-amber-400 animate-pulse";
  } else if (normalized === "failed") {
    className = "bg-rose-500/10 text-rose-400 border border-rose-500/25";
    dotClass = "bg-rose-400";
  } else if (normalized === "cancelled") {
    className = "bg-zinc-500/10 text-zinc-400 border border-zinc-500/25";
    dotClass = "bg-zinc-500";
  }

  return (
    <span className={`inline-flex items-center gap-1.5 rounded px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider tabular-nums ${className}`}>
      <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${dotClass}`} aria-hidden />
      {status}
    </span>
  );
}
