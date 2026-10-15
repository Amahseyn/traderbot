"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArtifactGallery } from "@/components/ArtifactGallery";
import { CompareSessionPanel } from "@/components/CompareSessionPanel";
import { RunAnalyticsPanel } from "@/components/RunAnalyticsPanel";
import { RunDetailOverview } from "@/components/RunDetailOverview";
import { TradeLogsTable } from "@/components/TradeLogsTable";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorState, PageSkeleton } from "@/components/ui/States";
import { api, apiUrl } from "@/lib/api";

export default function RunDetailPage() {
  const params = useParams();
  const runId = String(params.id);
  const [showRawMetrics, setShowRawMetrics] = useState(false);
  const runQuery = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId) });

  if (runQuery.isLoading) {
    return (
      <PageSkeleton />
    );
  }
  if (runQuery.isError || !runQuery.data) {
    return (
      <div className="space-y-4">
        <ErrorState
          title={runQuery.isError ? "Could not load this run" : "Run not found"}
          error={runQuery.error}
          action={
            <div className="flex flex-wrap gap-2">
              <Link href="/runs">
                <Button variant="secondary">Back to runs</Button>
              </Link>
              <Button variant="ghost" onClick={() => runQuery.refetch()}>
                Retry
              </Button>
            </div>
          }
        />
      </div>
    );
  }

  const run = runQuery.data;
  const titleParts = [run.symbol, run.strategy_id ?? run.model_id].filter(Boolean);
  const subtitle =
    run.dataset_label ??
    (run.run_kind === "strategy_backtest" ? "Strategy backtest" : "Run");

  return (
    <div className="space-y-8">
      <nav aria-label="Breadcrumb" className="text-muted -mb-4 text-xs">
        <Link href="/runs" className="hover:text-white">Runs</Link>
        <span className="mx-1.5">/</span>
        <span className="text-slate-300">{run.id.slice(0, 8)}</span>
      </nav>
      <PageHeader
        eyebrow="Review"
        title={titleParts.length > 0 ? titleParts.join(" · ") : `Run ${run.id.slice(0, 8)}…`}
        description={subtitle}
        actions={
          <>
            <Link href="/runs">
              <Button variant="secondary">All runs</Button>
            </Link>
            <a href={apiUrl(run.results_download_url)}>
              <Button variant="ghost">Download summary</Button>
            </a>
          </>
        }
      />

      <RunDetailOverview run={run} />

      {run.run_kind === "strategy_backtest" && <RunAnalyticsPanel runId={run.id} />}

      {run.run_kind === "strategy_backtest" && <TradeLogsTable metrics={run.metrics} />}

      {run.compare_session_id && run.run_kind === "strategy_backtest" && (
        <CompareSessionPanel
          sessionId={run.compare_session_id}
          currentRunId={run.id}
          symbol={run.symbol}
        />
      )}

      {(run.artifacts?.length ?? 0) > 0 && (
        <ArtifactGallery artifacts={run.artifacts!} title="Backtest charts" />
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Parameters" description="Strategy inputs and simulation settings recorded with this run.">
          <JsonBlock value={run.parameters} collapsed />
        </Card>
        <Card title="Data context" description="Dataset path, bar count, and market metadata.">
          <JsonBlock value={run.data_context} collapsed />
        </Card>
      </div>

      <Card
        title="Full metrics"
        description="Raw summary JSON from the backtest."
      >
        <Button
          type="button"
          variant="ghost"
          className="mb-3"
          onClick={() => setShowRawMetrics((open) => !open)}
        >
          {showRawMetrics ? "Hide JSON" : "Show JSON"}
        </Button>
        {showRawMetrics && <JsonBlock value={run.metrics} />}
        {!showRawMetrics && (
          <p className="text-muted text-sm">
            Key fields are summarized above. Expand JSON for vectorbt extras, paths, and compare
            metadata.
          </p>
        )}
      </Card>
    </div>
  );
}
