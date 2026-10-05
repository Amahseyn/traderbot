type StatusBadgeProps = {
  status: string;
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const normalized = status.toLowerCase();
  let className = "bg-slate-700/80 text-slate-200";
  if (normalized === "completed") {
    className = "bg-emerald-900/70 text-emerald-200";
  } else if (normalized === "running" || normalized === "queued") {
    className = "bg-amber-900/70 text-amber-200";
  } else if (normalized === "failed") {
    className = "bg-red-900/70 text-red-200";
  } else if (normalized === "cancelled") {
    className = "bg-slate-600/80 text-slate-200";
  }
  return <span className={`badge ${className}`}>{status}</span>;
}
