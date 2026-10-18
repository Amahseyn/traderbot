"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { StrategyParamFields } from "@/components/StrategyParamFields";
import { ErrorState } from "@/components/ui/States";
import { api } from "@/lib/api";

type OptimizedStrategyParamsBlockProps = {
  strategyId: string;
  symbol: string | null;
  resolution: string | null;
  datasetId?: string | null;
  useOptimized: boolean;
  onUseOptimizedChange: (value: boolean) => void;
  manualValues: Record<string, unknown>;
  onManualValuesChange: (values: Record<string, unknown>) => void;
};

export function OptimizedStrategyParamsBlock({
  strategyId,
  symbol,
  resolution,
  datasetId,
  useOptimized,
  onUseOptimizedChange,
  manualValues,
  onManualValuesChange,
}: OptimizedStrategyParamsBlockProps) {
  const fieldsQuery = useQuery({
    queryKey: ["strategy-params", strategyId],
    queryFn: () => api.strategyParams(strategyId),
    enabled: Boolean(strategyId),
  });

  const optimizedQuery = useQuery({
    queryKey: ["optimized-strategy-params", strategyId, symbol, resolution, datasetId, useOptimized],
    queryFn: () =>
      api.optimizedStrategyParams({
        strategyId,
        symbol: symbol ?? undefined,
        resolution: resolution ?? undefined,
        datasetId: datasetId ?? undefined,
      }),
    enabled: Boolean(strategyId) && useOptimized && Boolean(symbol || datasetId),
  });

  const fields = fieldsQuery.data?.params ?? [];
  const displayValues = useMemo(() => {
    if (useOptimized && optimizedQuery.data?.values) {
      return optimizedQuery.data.values;
    }
    return manualValues;
  }, [useOptimized, optimizedQuery.data?.values, manualValues]);

  useEffect(() => {
    if (!fieldsQuery.data?.params?.length || useOptimized) {
      return;
    }
    const initial: Record<string, unknown> = {};
    for (const field of fieldsQuery.data.params) {
      initial[field.name] = field.default;
    }
    onManualValuesChange(initial);
  }, [fieldsQuery.data, strategyId, useOptimized, onManualValuesChange]);

  function patchManual(name: string, value: unknown) {
    onManualValuesChange({ ...manualValues, [name]: value });
  }

  return (
    <div className="space-y-3">
      <label className="flex items-center gap-2 text-sm text-slate-200">
        <input
          type="checkbox"
          checked={useOptimized}
          onChange={(event) => onUseOptimizedChange(event.target.checked)}
        />
        Use stored sweep / robust defaults for this market and candle size
      </label>
      <p className="text-xs text-muted">
        Loads a prior grid result from the Lab store. It does not fetch new candles — use{" "}
        <span className="text-slate-300">Optimize before session</span> below to fit on the last 100
        closed bars (per market × interval) before trading starts.
      </p>
      {useOptimized && optimizedQuery.data?.sweep_meta?.sweep_fallback && (
        <p className="text-sm text-amber-200/90">
          No sweep stored for {optimizedQuery.data.sweep_meta.requested_symbol ?? "this market"} yet —
          showing params from {optimizedQuery.data.sweep_meta.sweep_symbol}. Run “Optimize before
          session” or a Lab sweep on this pair to tune locally.
        </p>
      )}
      {useOptimized &&
        optimizedQuery.data?.sweep_meta?.optimize_start_utc &&
        optimizedQuery.data?.sweep_meta?.optimize_end_utc && (
          <p className="text-sm text-muted">
            Params fit on {optimizedQuery.data.sweep_meta.optimize_start_utc} →{" "}
            {optimizedQuery.data.sweep_meta.optimize_end_utc}
            {optimizedQuery.data.sweep_meta.compare_start_utc
              ? ` (compare window ${optimizedQuery.data.sweep_meta.compare_start_utc} → ${
                  optimizedQuery.data.sweep_meta.compare_end_utc ?? "…"
                })`
              : null}
            .
          </p>
        )}
      {useOptimized && !symbol && !datasetId && (
        <p className="text-sm text-amber-200/90">Select a market or dataset to load tuned values.</p>
      )}
      {useOptimized && optimizedQuery.isFetching && (
        <p className="text-sm text-muted">Loading optimized parameters…</p>
      )}
      {useOptimized && optimizedQuery.isError && (
        <ErrorState title="Could not load optimized parameters" error={optimizedQuery.error} />
      )}
      {fields.length > 0 && (
        <StrategyParamFields
          fields={fields}
          values={displayValues}
          sources={useOptimized ? optimizedQuery.data?.sources : undefined}
          disabled={useOptimized}
          onChange={useOptimized ? undefined : patchManual}
        />
      )}
    </div>
  );
}
