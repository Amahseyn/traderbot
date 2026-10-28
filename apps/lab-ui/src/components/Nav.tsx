"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api, API_BASE } from "@/lib/api";

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

function IconMarketCap() {
  return (
    <svg className={iconClass} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden>
      <path d="M3 3v18h18" strokeLinecap="round" />
      <path d="M7 16v-4M12 16V8M17 16v-6" strokeLinecap="round" />
    </svg>
  );
}

const PRIMARY_LINKS: NavLink[] = [
  { href: "/", label: "Overview", description: "Stats and shortcuts", icon: <IconOverview /> },
  { href: "/marketcap", label: "Market Cap", description: "Global assets & screener", icon: <IconMarketCap /> },
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

function LabMark({ className = "" }: { className?: string }) {
  return (
    <div
      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border-bright bg-panel-elevated text-zinc-100 shadow-sm ${className}`}
    >
      <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" aria-hidden>
        <path
          d="M3 18h18M6 14l4-8 4 6 4-3"
          className="stroke-accent"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
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
    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/25"
    : loading
      ? "bg-amber-500/10 text-amber-400 border border-amber-500/25"
      : "bg-rose-500/10 text-rose-400 border border-rose-500/30";

  const dotTone = online ? "bg-emerald-400" : loading ? "bg-amber-400 animate-pulse" : "bg-rose-400";

  return (
    <span
      className={`hidden items-center gap-1.5 rounded px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-wider lg:inline-flex ${tone}`}
      title={label}
    >
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dotTone}`} aria-hidden />
      {online ? "API Online" : loading ? "Connecting…" : "API Offline"}
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
      className={`group flex items-center gap-1.5 rounded transition-colors duration-150 no-underline hover:no-underline ${
        compact ? "px-3 py-2 text-sm" : "px-2.5 py-1 text-xs"
      } ${
        active
          ? "bg-panel-elevated text-white font-medium border border-border-bright shadow-sm"
          : "text-zinc-400 hover:bg-panel-elevated/70 hover:text-zinc-200 border border-transparent"
      }`}
    >
      <span className={active ? "text-accent" : "text-zinc-500 group-hover:text-zinc-300 transition-colors duration-150"}>
        {link.icon}
      </span>
      <span className="font-medium tracking-tight">{link.label}</span>
      {compact && link.description && (
        <span className="ml-auto text-xs text-muted group-hover:text-zinc-400">{link.description}</span>
      )}
    </Link>
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
    <header className="sticky top-0 z-30 app-bar">
      <nav aria-label="Main" className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="flex h-14 items-center gap-4">
          <Link
            href="/"
            className="flex min-w-0 items-center gap-3 no-underline hover:no-underline"
          >
            <LabMark />
            <div className="min-w-0 leading-tight">
              <span className="block truncate text-sm font-semibold tracking-tight text-white sm:text-[15px]">
                <span className="hidden sm:inline">Traderbot Lab</span>
                <span className="sm:hidden">Lab</span>
              </span>
              <span className="hidden text-[11px] text-muted sm:block">Research & backtests</span>
            </div>
          </Link>

          <div className="hidden flex-1 justify-center lg:flex">
            <div className="nav-pill flex max-w-full items-center gap-1 overflow-x-auto [scrollbar-width:none]">
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
              className="inline-flex items-center justify-center rounded-lg border border-border bg-surface p-2.5 text-slate-200 transition-colors duration-150 hover:border-border-bright hover:text-white lg:hidden"
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
          className="border-t border-border bg-surface lg:hidden"
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
    </header>
  );
}
