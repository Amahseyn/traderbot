"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { JobMonitor } from "@/components/JobMonitor";
import { OptimizedStrategyParamsBlock } from "@/components/OptimizedStrategyParamsBlock";
import { OptimizerBatchPanel } from "@/components/OptimizerBatchPanel";
import { OptimizerMarketPipelines } from "@/components/OptimizerMarketPipelines";
import { OptimizerSweepsTable } from "@/components/OptimizerSweepsTable";
import {
  StrategySweepForm,
  type StrategySweepSelection,
} from "@/components/StrategySweepForm";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Page } from "@/components/ui/Page";
import { PageHeader } from "@/components/ui/PageHeader";

type OptimizerSection = "single" | "batch" | "pipelines";

export default function OptimizerPage() {
  const queryClient = useQueryClient();
  const [jobId, setJobId] = useState<string | null>(null);
  const [section, setSection] = useState<OptimizerSection>("single");
  const [selection, setSelection] = useState<StrategySweepSelection>({
    datasetId: "",
    strategyId: "",
    symbol: null,
    resolution: null,
  });
  const [useStoredParams, setUseStoredParams] = useState(true);
  const [manualParams, setManualParams] = useState<Record<string, unknown>>({});

  const onJob = useCallback(
    (id: string) => {
      setJobId(id);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      void queryClient.invalidateQueries({ queryKey: ["sweeps"] });
    },
    [queryClient],
  );

  const onSelectionChange = useCallback((next: StrategySweepSelection) => {
    setSelection(next);
  }, []);

  const tabs: { id: OptimizerSection; label: string; hint: string; blurb: string }[] = [
    {
      id: "single",
      label: "Single sweep",
      hint: "One dataset × one strategy",
      blurb: "Search a market, pick the matching OHLC file, then run Optuna or a small grid on one strategy.",
    },
    {
      id: "batch",
      label: "Batch",
      hint: "Many files × many strategies",
      blurb: "Filter the catalog by market search, select files, then Optuna every chosen strategy and compare winners.",
    },
    {
      id: "pipelines",
      label: "Market pipelines",
      hint: "Export + Optuna + compare",
      blurb: "End-to-end Hyperliquid research: export fresh bars, tune all rule strategies, rank results.",
    },
  ];

  useEffect(() => {
    const hash = window.location.hash.replace("#", "") as OptimizerSection;
    if (hash === "single" || hash === "batch" || hash === "pipelines") {
      setSection(hash);
    }
  }, []);

  const setSectionWithHash = useCallback((next: OptimizerSection) => {
    setSection(next);
    window.history.replaceState(null, "", `#${next}`);
  }, []);

  const activeTab = tabs.find((tab) => tab.id === section);

  return (
    <Page className="space-y-6 sm:space-y-8 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)] lg:items-start lg:gap-8 lg:space-y-0">
      <div className="space-y-8 min-w-0">
        <PageHeader
          eyebrow="Parameter search"
          title="Optimizer"
          description="Optuna tunes strategy parameters on catalog OHLC (validation split). Grid mode sweeps one or two knobs. Batch and market pipelines scale to many strategies and markets."
          actions={
            <Link href="/data">
              <Button variant="secondary">Export data</Button>
            </Link>
          }
        />

        <div className="space-y-2">
          <div className="tab-list flex flex-wrap gap-1">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`tab ${section === tab.id ? "tab-active" : ""}`}
                onClick={() => setSectionWithHash(tab.id)}
                title={tab.hint}
              >
                {tab.label}
              </button>
            ))}
          </div>
          {activeTab && <p className="text-sm text-muted">{activeTab.blurb}</p>}
        </div>

        {section === "single" && (
          <Card
            title="Single dataset optimizer"
            description="POST strategy-sweep — Optuna explores the full strategy search space; results are stored for Live and Custom research."
          >
            <StrategySweepForm onJob={onJob} onSelectionChange={onSelectionChange} />
          </Card>
        )}

        {section === "batch" && (
          <Card
            title="Batch Optuna on catalog files"
            description="Runs custom-research: for each selected CSV, Optuna every chosen strategy, then strategy compare with sweep winners."
          >
            <OptimizerBatchPanel onJob={onJob} />
          </Card>
        )}

        {section === "pipelines" && (
          <Card
            title="Hyperliquid market research"
            description="Named pipelines export OHLC, Optuna all rule-based strategies per interval, then rank strategies."
          >
            <OptimizerMarketPipelines onJob={onJob} />
          </Card>
        )}

        {section === "single" && selection.strategyId && (
          <Card
            title="Stored parameters"
            description="Values loaded from the sweep store for the dataset symbol and resolution."
          >
            <OptimizedStrategyParamsBlock
              strategyId={selection.strategyId}
              symbol={selection.symbol}
              resolution={selection.resolution}
              datasetId={selection.datasetId}
              useOptimized={useStoredParams}
              onUseOptimizedChange={setUseStoredParams}
              manualValues={manualParams}
              onManualValuesChange={setManualParams}
            />
          </Card>
        )}

        <Card title="Recent sweeps" description="Latest rows from the Lab sweep store (newest first).">
          <OptimizerSweepsTable limit={30} />
        </Card>

        <p className="text-sm text-muted">
          Full multi-step research (export + compare without optimizer focus) lives on{" "}
          <Link href="/custom" className="text-accent hover:underline">Custom research</Link>.
          Quick backtest jobs remain under{" "}
          <Link href="/custom#quick-jobs" className="text-accent hover:underline">Custom → Quick jobs</Link>.
        </p>
      </div>

      <div className="lg:sticky lg:top-24 lg:max-h-[calc(100vh-7rem)] lg:overflow-y-auto lg:space-y-4">
        <JobMonitor activeJobId={jobId} onSelectJob={setJobId} />
      </div>
    </Page>
  );
}
