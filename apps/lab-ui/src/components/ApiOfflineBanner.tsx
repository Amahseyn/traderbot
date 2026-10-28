"use client";

import { useQuery } from "@tanstack/react-query";
import { api, API_BASE } from "@/lib/api";

export function ApiOfflineBanner() {
  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 15_000,
    retry: 1,
  });

  if (healthQuery.isLoading || healthQuery.isSuccess) {
    return null;
  }

  return (
    <div
      className="border-b border-red-500/30 bg-red-500/10 px-4 py-2.5 text-center text-sm text-red-100 sm:px-6"
      role="alert"
    >
      Lab API unreachable at <code className="text-red-100">{API_BASE}</code>. Start{" "}
      <code className="text-red-100">./run-lab.sh</code> or{" "}
      <code className="text-red-100">./run-lab-api.sh</code>, then refresh.
    </div>
  );
}
