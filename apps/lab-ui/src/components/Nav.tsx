"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api, API_BASE } from "@/lib/api";

type NavLink = { href: string; label: string };

const LOOP_LINKS: NavLink[] = [
  { href: "/data", label: "Data" },
  { href: "/experiments", label: "Lab" },
  { href: "/custom", label: "Custom" },
  { href: "/runs", label: "Runs" },
  { href: "/configs", label: "Configs" },
];

const TOOL_LINKS: NavLink[] = [{ href: "/settings", label: "Settings" }];

function NavItem({ link, active }: { link: NavLink; active: boolean }) {
  return (
    <Link
      href={link.href}
      className={`shrink-0 rounded-lg px-3 py-1.5 text-sm transition ${
        active
          ? "bg-accent/20 text-white ring-1 ring-accent/30"
          : "text-slate-300 hover:bg-surface hover:text-white"
      }`}
    >
      {link.label}
    </Link>
  );
}

function isActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

function ApiStatusDot() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 30_000,
    retry: 1,
  });

  const online = healthQuery.isSuccess && healthQuery.data?.status === "ok";
  const label = online
    ? "Lab API connected"
    : healthQuery.isLoading
      ? "Checking Lab API…"
      : `Lab API offline (${API_BASE})`;

  return (
    <span
      className={`mr-2 inline-block h-2 w-2 shrink-0 rounded-full ${
        online ? "bg-emerald-400" : healthQuery.isLoading ? "bg-amber-400" : "bg-red-500"
      }`}
      title={label}
      aria-label={label}
    />
  );
}

export function Nav() {
  const pathname = usePathname();

  return (
    <nav className="sticky top-0 z-20 border-b border-border bg-panel/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-1 px-6 py-3">
        <Link
          href="/"
          className="mr-2 flex items-center font-semibold text-white tracking-tight shrink-0"
          title="Overview"
        >
          <ApiStatusDot />
          Traderbot Lab
        </Link>

        {LOOP_LINKS.map((link) => (
          <NavItem key={link.href} link={link} active={isActive(pathname, link.href)} />
        ))}
        <span className="ml-auto flex items-center gap-1">
          <span className="mx-1 h-4 w-px shrink-0 bg-border" aria-hidden />
          {TOOL_LINKS.map((link) => (
            <NavItem key={link.href} link={link} active={isActive(pathname, link.href)} />
          ))}
        </span>
      </div>
    </nav>
  );
}
