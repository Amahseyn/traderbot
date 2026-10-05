/**
 * useLogs Hook — Fetch and search logs (non-streaming version)
 *
 * Use when you want on-demand log retrieval instead of streaming.
 */

import { useEffect, useState, useCallback } from "react";
import { API_BASE } from "@/lib/api";

export interface LogEntry {
  timestamp: number;
  timestamp_iso: string;
  level: string;
  module: string;
  message: string;
  context: Record<string, unknown>;
  source: string;
}

export interface LogStats {
  total: number;
  by_level: Record<string, number>;
  unique_modules: number;
  unique_sources: number;
  time_span_seconds: number;
}

export function useLogs() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [stats, setStats] = useState<LogStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRecent = useCallback(
    async (
      limit: number = 100,
      level?: string,
      module?: string,
      source?: string
    ) => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        params.append("limit", limit.toString());
        if (level) params.append("level", level);
        if (module) params.append("module", module);
        if (source) params.append("source", source);

        const response = await fetch(`${API_BASE}/api/logs/recent?${params}`);
        if (!response.ok) throw new Error("Failed to fetch logs");

        const data = await response.json();
        setLogs(data.logs || []);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const search = useCallback(
    async (query: string, limit: number = 100) => {
      setLoading(true);
      try {
        const params = new URLSearchParams();
        params.append("query", query);
        params.append("limit", limit.toString());

        const response = await fetch(`${API_BASE}/api/logs/search?${params}`);
        if (!response.ok) throw new Error("Search failed");

        const data = await response.json();
        setLogs(data.results || []);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const fetchStats = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/logs/stats`);
      if (!response.ok) throw new Error("Failed to fetch stats");

      const data = await response.json();
      setStats(data.stats);
    } catch (err) {
      console.error("Stats fetch failed:", err);
    }
  }, []);

  return {
    logs,
    stats,
    loading,
    error,
    fetchRecent,
    search,
    fetchStats,
  };
}
