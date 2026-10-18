"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api, API_BASE } from "@/lib/api";
import { WORKFLOW_STEPS, type WorkflowStepId } from "@/lib/workflow";

type NavLink = {
  href: string;
  label: string;
  description?: string;
  icon: ReactNode;
};

const iconClass = "h-4 w-4 shrink-0 opacity-90";

function IconOverview() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M4 10.5L12 4l8 6.5V20a1 1 0 01-1 1h-5v-6H10v6H5a1 1 0 01-1-1v-9.5z" strokeLinejoin="round" />
    </svg>
  );
}

function IconData() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <ellipse cx="12" cy="6" rx="8" ry="3" />
      <path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
    </svg>
  );
}

function IconResearch() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M9 3h6l1 7H8L9 3zM7 10h10l-1 11H8L7 10z" strokeLinejoin="round" />
      <path d="M10 14h4" strokeLinecap="round" />
    </svg>
  );
}

function IconOptimizer() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1" strokeLinecap="round" />
      <circle cx="12" cy="12" r="4" />
    </svg>
  );
}

function IconStrategies() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M4 7h16M4 12h10M4 17h14" strokeLinecap="round" />
      <circle cx="19" cy="12" r="2" fill="currentColor" stroke="none" className="opacity-80" />
    </svg>
  );
}

function IconLive() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M13 2L4 14h7l-1 8 10-14h-7l0-6z" strokeLinejoin="round" />
    </svg>
  );
}

function IconRuns() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" strokeLinecap="round" />
    </svg>
  );
}

function IconSettings() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <circle cx="12" cy="12" r="3" />
      <path
        d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32l1.41 1.41M2 12h2m16 0h2M4.93 19.07l1.41-1.41M18.36 5.64l1.41-1.41"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconNew() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M12 5v14M5 12h14" strokeLinecap="round" />
    </svg>
  );
}

const PRIMARY_LINKS: NavLink[] = [
  { href: "/", label: "Overview", description: "Stats and shortcuts", icon: <IconOverview /> },
  { href: "/new", label: "New", description: "Discovery & jobs", icon: <IconNew /> },
  { href: "/data", label: "Data", description: "Export OHLC & catalog", icon: <IconData /> },
  { href: "/custom", label: "Research", description: "Multi-file pipeline", icon: <IconResearch /> },
  { href: "/optimizer", label: "Optimizer", description: "Optuna & sweeps", icon: <IconOptimizer /> },
  { href: "/strategies", label: "Strategies", description: "Rule catalog", icon: <IconStrategies /> },
  { href: "/live", label: "Live", description: "Paper & live sessions", icon: <IconLive /> },
  { href: "/runs", label: "Runs", description: "Results & trade logs", icon: <IconRuns /> },
];

const TOOL_LINKS: NavLink[] = [
  { href: "/settings", label: "Settings", description: "API auth & keys", icon: <IconSettings /> },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

function activeWorkflowStep(pathname: string): WorkflowStepId | null {
  if (pathname === "/") {
    return "overview";
  }
  for (const step of WORKFLOW_STEPS) {
    if (step.matchPrefixes.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`))) {
      return step.id;
    }
  }
  return null;
}

function LabMark({ className = "" }: { className?: string }) {
  return (
    <div
      className={`relative flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-accent/30 via-accent/15 to-indigo-500/20 shadow-glow-sm ring-1 ring-accent/30 ${className}`}
    >
      <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" aria-hidden>
        <path
          d="M6 18V8l3 4.5L12 8l3 4.5L18 8v10"
          className="stroke-white"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="absolute -inset-px rounded-xl bg-gradient-to-br from-white/20 to-transparent opacity-40" aria-hidden />
    </div>
  );
}

function ApiStatusBadge() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
    retry: 1,
  });

  const online = healthQuery.isSuccess && healthQuery.data?.status === "ok";
  const loading = healthQuery.isLoading;
  const label = online
    ? "Lab API connected"
    : loading
      ? "Checking Lab API…"
      : `Lab API offline (${API_BASE})`;

  const tone = online
    ? "from-emerald-500/20 to-emerald-500/5 text-emerald-100 ring-emerald-400/25"
    : loading
      ? "from-amber-500/20 to-amber-500/5 text-amber-50 ring-amber-400/25"
      : "from-red-500/20 to-red-500/5 text-red-100 ring-red-400/30";

  const dotTone = online ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]" : loading ? "bg-amber-400 animate-pulse" : "bg-red-400";

  return (
    <span
      className={`hidden items-center gap-2 rounded-full bg-gradient-to-r px-3 py-1.5 text-[11px] font-medium ring-1 lg:inline-flex ${tone}`}
      title={label}
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotTone}`} aria-hidden />
      {online ? "API online" : loading ? "Checking…" : "API offline"}
    </span>
  );
}

function NavItem({
  link,
  active,
  onNavigate,
  compact,
}: {
  link: NavLink;
  active: boolean;
  onNavigate?: () => void;
  compact?: boolean;
}) {
  return (
    <Link
      href={link.href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={`group flex items-center gap-2 rounded-full transition duration-200 no-underline hover:no-underline ${
        compact ? "px-3 py-2.5" : "px-3 py-1.5"
      } ${
        active
          ? "bg-gradient-to-b from-accent/35 to-accent/15 text-white shadow-sm ring-1 ring-accent/40"
          : "text-slate-300 hover:bg-white/[0.06] hover:text-white"
      }`}
    >
      <span className={active ? "text-white" : "text-slate-400 group-hover:text-accent"}>{link.icon}</span>
      <span className={`${compact ? "text-sm font-medium" : "text-[13px] font-medium"}`}>{link.label}</span>
      {compact && link.description && (
        <span className="ml-auto text-xs text-muted group-hover:text-slate-400">{link.description}</span>
      )}
    </Link>
  );
}

function WorkflowStrip({ pathname }: { pathname: string }) {
  const current = activeWorkflowStep(pathname);
  if (!current) {
    return null;
  }

  const steps = WORKFLOW_STEPS.filter((step) => step.id !== "overview");
  const currentIndex = steps.findIndex((step) => step.id === current);

  return (
    <div className="border-t border-white/[0.04] bg-gradient-to-r from-surface/80 via-panel/40 to-surface/80" aria-label="Research workflow">
      <ol className="mx-auto flex max-w-7xl items-center gap-2 overflow-x-auto px-4 py-2.5 sm:px-6 [scrollbar-width:none]">
        {steps.map((step, index) => {
          const active = current === step.id;
          const complete = current !== "overview" && currentIndex > index;
          return (
            <li key={step.id} className="flex shrink-0 items-center gap-2">
              {index > 0 && (
                <span
                  className={`h-px w-6 sm:w-10 ${complete ? "bg-gradient-to-r from-accent/60 to-accent/20" : "bg-border/80"}`}
                  aria-hidden
                />
              )}
              <Link
                href={step.href}
                className={`flex items-center gap-2 rounded-full px-2.5 py-1 transition duration-200 no-underline hover:no-underline sm:px-3 sm:py-1.5 ${
                  active
                    ? "bg-accent/15 text-white ring-1 ring-accent/35 shadow-glow-sm"
                    : complete
                      ? "text-accent hover:bg-accent/10"
                      : "text-muted hover:bg-white/[0.04] hover:text-slate-200"
                }`}
              >
                <span
                  className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold ${
                    active
                      ? "bg-gradient-to-br from-accent to-accent-dim text-white shadow-glow-sm"
                      : complete
                        ? "bg-accent/20 text-accent ring-1 ring-accent/30"
                        : "bg-surface text-muted ring-1 ring-border"
                  }`}
                >
                  {index + 1}
                </span>
                <span className="text-xs font-medium sm:text-[13px]">
                  <span className="text-muted/90 sm:hidden">{step.short}</span>
                  <span className="hidden sm:inline">{step.label}</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function Nav() {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!mobileOpen) {
      return;
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMobileOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  return (
    <header className="sticky top-0 z-30 glass-panel">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/40 to-transparent" aria-hidden />
      <nav aria-label="Main" className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="flex h-[3.75rem] items-center gap-4">
          <Link
            href="/"
            className="flex min-w-0 items-center gap-3 no-underline hover:no-underline"
          >
            <LabMark />
            <div className="min-w-0 leading-tight">
              <span className="block truncate text-sm font-semibold tracking-tight text-gradient sm:text-[15px]">
                <span className="hidden sm:inline">Traderbot Lab</span>
                <span className="sm:hidden">Lab</span>
              </span>
              <span className="hidden text-[11px] text-muted sm:block">Research & backtests</span>
            </div>
          </Link>

          <div className="hidden flex-1 justify-center lg:flex">
            <div className="nav-pill flex max-w-full items-center gap-0.5 overflow-x-auto [scrollbar-width:none]">
              {PRIMARY_LINKS.map((link) => (
                <NavItem key={link.href} link={link} active={isActive(pathname, link.href)} />
              ))}
            </div>
          </div>

          <div className="ml-auto flex items-center gap-2">
            <ApiStatusBadge />
            <div className="hidden items-center gap-1 md:flex">
              {TOOL_LINKS.map((link) => (
                <NavItem key={link.href} link={link} active={isActive(pathname, link.href)} />
              ))}
            </div>
            <button
              type="button"
              className="inline-flex items-center justify-center rounded-xl border border-border/80 bg-surface/80 p-2.5 text-slate-200 shadow-card transition hover:border-accent/40 hover:text-white lg:hidden"
              aria-expanded={mobileOpen}
              aria-controls="mobile-nav-panel"
              onClick={() => setMobileOpen((open) => !open)}
            >
              <span className="sr-only">{mobileOpen ? "Close menu" : "Open menu"}</span>
              {mobileOpen ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                  <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                  <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </nav>

      {mobileOpen && (
        <div
          id="mobile-nav-panel"
          className="border-t border-white/[0.05] bg-panel/95 backdrop-blur-xl lg:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation menu"
        >
          <div className="mx-auto max-w-7xl space-y-1 px-4 py-4 sm:px-6">
            {PRIMARY_LINKS.map((link) => (
              <NavItem
                key={link.href}
                link={link}
                active={isActive(pathname, link.href)}
                onNavigate={() => setMobileOpen(false)}
                compact
              />
            ))}
            <div className="my-3 h-px bg-border/60" aria-hidden />
            {TOOL_LINKS.map((link) => (
              <NavItem
                key={link.href}
                link={link}
                active={isActive(pathname, link.href)}
                onNavigate={() => setMobileOpen(false)}
                compact
              />
            ))}
            <p className="px-3 pt-3 text-[11px] text-muted">
              API{" "}
              <code className="rounded-md bg-surface px-1.5 py-0.5 font-mono text-slate-400">{API_BASE}</code>
            </p>
          </div>
        </div>
      )}

      <WorkflowStrip pathname={pathname} />
    </header>
  );
}
