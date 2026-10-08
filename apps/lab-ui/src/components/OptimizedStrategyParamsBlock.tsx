"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";
import { StrategyParamFields } from "@/components/StrategyParamFields";
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
        Use robust optimized defaults (sweep winner requires separate approval)
      </label>
      {useOptimized && !symbol && !datasetId && (
        <p className="text-sm text-amber-200/90">Select a market or dataset to load tuned values.</p>
      )}
      {useOptimized && optimizedQuery.isFetching && (
        <p className="text-sm text-muted">Loading optimized parameters…</p>
      )}
      {useOptimized && optimizedQuery.isError && (
        <p className="text-sm text-red-400">
          {optimizedQuery.error instanceof Error
            ? optimizedQuery.error.message
            : "Could not load optimized parameters."}
        </p>
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
