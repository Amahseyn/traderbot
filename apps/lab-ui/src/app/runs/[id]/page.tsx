"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArtifactGallery } from "@/components/ArtifactGallery";
import { CompareSessionPanel } from "@/components/CompareSessionPanel";
import { RunDetailOverview } from "@/components/RunDetailOverview";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { JsonBlock } from "@/components/ui/JsonBlock";
import { PageHeader } from "@/components/ui/PageHeader";
import { api, apiUrl } from "@/lib/api";

export default function RunDetailPage() {
  const params = useParams();
  const runId = String(params.id);
  const [showRawMetrics, setShowRawMetrics] = useState(false);
  const runQuery = useQuery({ queryKey: ["run", runId], queryFn: () => api.run(runId) });

  if (runQuery.isLoading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-10 w-2/3 rounded-lg bg-panel" />
        <div className="h-40 rounded-xl bg-panel" />
        <div className="h-64 rounded-xl bg-panel" />
      </div>
    );
  }
  if (runQuery.isError || !runQuery.data) {
    return (
      <div className="space-y-4">
        <p className="text-red-400">Run not found.</p>
        <Link href="/runs">
          <Button variant="secondary">Back to runs</Button>
        </Link>
      </div>
    );
  }

  const run = runQuery.data;
  const titleParts = [run.symbol, run.strategy_id ?? run.model_id].filter(Boolean);
  const subtitle =
    run.dataset_label ??
    (run.run_kind === "strategy_backtest" ? "Strategy backtest" : "ML forecast run");

  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="4 · Review"
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
        <Card title="Parameters" description="Strategy or model configuration stored with this run.">
          <JsonBlock value={run.parameters} />
        </Card>
        <Card title="Data context" description="Bars and market metadata used for evaluation.">
          <JsonBlock value={run.data_context} />
        </Card>
      </div>

      <Card
        title="Full metrics"
        description="Raw summary JSON from the backtest or forecast eval."
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
