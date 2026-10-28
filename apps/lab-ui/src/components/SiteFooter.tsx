import Link from "next/link";
import { API_BASE } from "@/lib/api";

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-border bg-surface">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="space-y-2">
          <p className="text-sm font-semibold text-white">Traderbot Lab</p>
          <p className="max-w-sm text-xs leading-relaxed text-muted">
            Export market data, run research pipelines, and review backtests — one cohesive workflow.
          </p>
        </div>
        <div className="flex flex-col gap-3 text-xs text-muted sm:items-end">
          <p className="flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-panel px-2 py-0.5 text-xs text-muted ring-1 ring-border">Lab API</span>
            <code className="rounded-md bg-panel px-2 py-1 font-mono text-[11px] text-slate-300 border border-border">
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
