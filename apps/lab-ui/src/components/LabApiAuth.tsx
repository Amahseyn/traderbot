"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";

export const labUiTokenConfigured = Boolean(process.env.NEXT_PUBLIC_LAB_API_TOKEN?.trim());

/** Shown under layout when POST/auth will fail until the browser token is set. */
export function LabAuthBanner() {
  const statusQuery = useQuery({
    queryKey: ["auth-status"],
    queryFn: api.authStatus,
    staleTime: 60_000,
  });

  if (statusQuery.data?.lab_api_token_configured !== true || labUiTokenConfigured) {
    return null;
  }

  return (
    <div
      className="border-b border-amber-500/25 bg-amber-500/10 px-4 py-2.5 text-center text-sm text-amber-100 sm:px-6"
      role="status"
    >
      Lab API auth is enabled. Set <code className="text-amber-50">NEXT_PUBLIC_LAB_API_TOKEN</code> in the UI
      build to match the API — see{" "}
      <Link href="/settings" className="font-medium text-amber-50 underline hover:no-underline">
        Settings
      </Link>
      .
    </div>
  );
}

export function LabApiAuthHint() {
  return (
    <p className="mt-2 text-sm text-muted">
      Set <code className="text-xs">NEXT_PUBLIC_LAB_API_TOKEN</code> to match the Lab API, then restart the UI.{" "}
      <Link href="/settings" className="text-accent hover:underline">Settings</Link>
    </p>
  );
}
