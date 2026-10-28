"use client";

import { useQuery } from "@tanstack/react-query";
import {
  DiscoveryMacroCards,
  DiscoveryMarketStructureSnippet,
  DiscoveryRankingsBlock,
  DiscoveryRunConfigSummary,
  DiscoveryScreenerPresetTable,
  DiscoverySentimentSnippet,
  DiscoverySummaryStats,
  DiscoveryTrendScannerTable,
} from "@/components/DiscoveryReportSections";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/States";
import { api, artifactUrl, withLabAuth } from "@/lib/api";
import type { OpportunityDiscoveryReport } from "@/lib/opportunityDiscoveryLog";
import {
  extractDiscoveryErrorLogLines,
  parseDiscoveryArtifactPath,
} from "@/lib/opportunityDiscoveryLog";

type DiscoveryJobResultsProps = {
  jobId: string | null;
  title?: string;
  highlightSymbols?: string[];
};

export function DiscoveryJobResults({
  jobId,
  title = "Discovery results",
  highlightSymbols,
}: DiscoveryJobResultsProps) {
  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.job(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status ?? "";
      return status === "queued" || status === "running" ? 2000 : false;
    },
  });

  const status = jobQuery.data?.status;
  const artifactPath = parseDiscoveryArtifactPath(jobQuery.data?.log_text ?? "");
  const jobCompleted = status === "completed";

  const dbRunQuery = useQuery({
    queryKey: ["discovery-run-by-job", jobId],
    queryFn: () => api.discoveryRunByJob(jobId!),
    enabled: Boolean(jobId) && jobCompleted,
    retry: false,
  });

  const artifactReportQuery = useQuery({
    queryKey: ["discovery-report-artifact", artifactPath],
    queryFn: async () => {
      const response = await fetch(artifactUrl(artifactPath!), withLabAuth());
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      return (await response.json()) as OpportunityDiscoveryReport;
    },
    enabled: Boolean(artifactPath) && jobCompleted && !dbRunQuery.data?.report,
  });

  const report: OpportunityDiscoveryReport | undefined =
    dbRunQuery.data?.report ?? artifactReportQuery.data;

  if (!jobId) {
    return null;
  }

  const summary = report?.summary;
  const errorLog = extractDiscoveryErrorLogLines(jobQuery.data?.log_text ?? "").join("\n");
  const reportLoading =
    jobCompleted && !report && (dbRunQuery.isLoading || artifactReportQuery.isLoading);

  return (
    <Card
      title={title}
      description={
        report?.config?.scan_kind === "coinbeacon_market"
          ? "CoinBeacon screener + trend rankings (Binance USDT perps). No strategy backtests."
          : "Market discovery rankings."
      }
    >
      {(status === "queued" || status === "running") && (
        <p className="text-sm text-muted">Job {jobId.slice(0, 8)}… is {status}. Logs update in the monitor.</p>
      )}
      {status === "failed" && (
        <p className="text-sm text-red-200/90">Discovery job failed. See the job log for details.</p>
      )}
      {errorLog && (
        <div className="mb-4 space-y-1">
          <p className="text-xs font-medium text-red-300/90">Error log</p>
          <pre
            className="max-h-56 overflow-auto rounded-lg border border-red-900/60 bg-red-950/30 p-3 text-xs whitespace-pre-wrap font-mono text-red-100/95"
          >
            {errorLog}
          </pre>
        </div>
      )}
      {report && <DiscoveryRunConfigSummary report={report} />}
      {report && <DiscoveryMacroCards report={report} />}
      {summary && <DiscoverySummaryStats summary={summary} />}
      {report && <DiscoverySentimentSnippet report={report} />}
      {report && <DiscoveryMarketStructureSnippet report={report} />}
      {report && <DiscoveryScreenerPresetTable report={report} />}
      {report && <DiscoveryTrendScannerTable report={report} />}
      {reportLoading && <Skeleton className="h-32 w-full" />}
      {!reportLoading && jobCompleted && !report && (dbRunQuery.error || artifactReportQuery.error) && (
        <p className="text-sm text-amber-200/90">
          Could not load discovery report from the database or artifact. Check the job log.
        </p>
      )}
      {!reportLoading && jobCompleted && !report && !dbRunQuery.error && !artifactReportQuery.error && (
        <p className="text-sm text-muted">
          Job completed but no discovery report was found. The artifact may not have been written —
          check the job log for details.
        </p>
      )}
      {artifactPath && jobCompleted && (
        <p className="mb-3 text-xs text-muted">
          {dbRunQuery.data?.report ? "Stored in Lab database" : "Loaded from artifact"} ·{" "}
          <a className="text-accent hover:underline" href={artifactUrl(artifactPath)} target="_blank" rel="noreferrer">
            discovery_report.json
          </a>
        </p>
      )}
      {report && <DiscoveryRankingsBlock report={report} highlightSymbols={highlightSymbols} />}
    </Card>
  );
}
