/**
 * Real-time Metrics Dashboard Hook
 *
 * Polls /api/infrastructure/metrics and displays:
 * - Cache hit rate
 * - Job throughput
 * - Prediction latency
 * - Memory usage
 */

import { useEffect, useState, useCallback } from "react";
import { API_BASE } from "@/lib/api";

export interface MetricsPoint {
  name: string;
  value: number;
  timestamp: number;
  tags: Record<string, string>;
}

export interface MetricsSummary {
  count: number;
  min: number;
  max: number;
  mean: number;
  latest: number;
}

export interface MetricsData {
  metrics: MetricsPoint[];
  summary: Record<string, MetricsSummary>;
  gauges: Record<string, number>;
}

export function useMetrics(pollIntervalMs: number = 5000) {
  const [data, setData] = useState<MetricsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    try {
      const [metricsRes, gaugesRes] = await Promise.all([
        fetch(`${API_BASE}/api/infrastructure/metrics/recent?since_seconds=60`),
        fetch(`${API_BASE}/api/infrastructure/metrics/gauges`),
      ]);

      if (!metricsRes.ok || !gaugesRes.ok) {
        throw new Error(`HTTP ${metricsRes.status || gaugesRes.status}`);
      }

      const [metrics, gauges] = await Promise.all([
        metricsRes.json(),
        gaugesRes.json(),
      ]);

      setData({
        metrics: metrics.metrics || [],
        summary: metrics.summary || {},
        gauges,
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
    const interval = setInterval(fetchMetrics, pollIntervalMs);
    return () => clearInterval(interval);
  }, [pollIntervalMs, fetchMetrics]);

  return { data, loading, error, refetch: fetchMetrics };
}
