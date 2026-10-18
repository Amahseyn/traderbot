import Link from "next/link";
import { API_BASE } from "@/lib/api";

export function SiteFooter() {
  return (
    <footer className="relative mt-auto border-t border-white/[0.05] bg-panel/40 backdrop-blur-sm">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/25 to-transparent" aria-hidden />
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="space-y-2">
          <p className="text-sm font-semibold text-gradient">Traderbot Lab</p>
          <p className="max-w-sm text-xs leading-relaxed text-muted">
            Export market data, run research pipelines, and review backtests — one cohesive workflow.
          </p>
        </div>
        <div className="flex flex-col gap-3 text-xs text-muted sm:items-end">
          <p className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-surface/80 px-2 py-0.5 ring-1 ring-border/80">Lab API</span>
            <code className="rounded-lg bg-surface/90 px-2 py-1 font-mono text-[11px] text-slate-300 ring-1 ring-border/60">
              {API_BASE}
            </code>
          </p>
          <nav aria-label="Footer" className="flex flex-wrap gap-x-5 gap-y-1">
            {[
              { href: "/data", label: "Data" },
              { href: "/custom", label: "Research" },
              { href: "/live", label: "Live" },
              { href: "/runs", label: "Runs" },
              { href: "/settings", label: "Settings" },
            ].map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-slate-400 transition hover:text-accent no-underline hover:no-underline"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </footer>
  );
}
