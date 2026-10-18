"use client";

import { useQuery } from "@tanstack/react-query";
import { api, artifactUrl, withLabAuth } from "@/lib/api";
import type { OpportunityDiscoveryReport } from "@/lib/opportunityDiscoveryLog";
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
import { Button } from "@/components/ui/Button";
import { ErrorState, Skeleton, TableSkeleton } from "@/components/ui/States";
import { formatUtcTimestamp } from "@/lib/format";

type DiscoveryRunsHistoryProps = {
  limit?: number;
  selectedRunId: string | null;
  onSelectRun: (runId: string | null, jobId: string | null) => void;
  highlightSymbols?: string[];
};

export function DiscoveryRunsHistory({
  limit = 20,
  selectedRunId,
  onSelectRun,
  highlightSymbols,
}: DiscoveryRunsHistoryProps) {
  const runsQuery = useQuery({
    queryKey: ["discovery-runs", limit],
    queryFn: () => api.discoveryRuns(limit),
    staleTime: 15_000,
  });

  const selected = runsQuery.data?.find((row) => row.id === selectedRunId) ?? null;

  const dbRunQuery = useQuery({
    queryKey: ["discovery-run", selectedRunId],
    queryFn: () => api.discoveryRun(selectedRunId!),
    enabled: Boolean(selectedRunId),
  });

  const artifactReportQuery = useQuery({
    queryKey: ["discovery-report-artifact", selected?.artifact_path],
    queryFn: async () => {
      const path = selected!.artifact_path!;
      const response = await fetch(artifactUrl(path), withLabAuth());
      if (!response.ok) {
        throw new Error(`${response.status} ${response.statusText}`);
      }
      return (await response.json()) as OpportunityDiscoveryReport;
    },
    enabled: Boolean(selected?.artifact_path) && !dbRunQuery.data?.report,
  });

  const report = dbRunQuery.data?.report ?? artifactReportQuery.data;

  if (runsQuery.isLoading) {
    return <TableSkeleton rows={4} />;
  }
  if (runsQuery.error) {
    return <ErrorState title="Could not load discovery history" error={runsQuery.error} />;
  }

  const rows = runsQuery.data ?? [];

  return (
    <div className="space-y-4">
      <Card
        title="Past discovery runs"
        description="Re-open a completed scan from the Lab database (no extra CoinBeacon credits)."
      >
        {rows.length === 0 ? (
          <p className="text-sm text-muted">No discovery runs yet. Start a scan above.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="data w-full text-sm">
              <thead>
                <tr>
                  <th>Finished</th>
                  <th>Exchange</th>
                  <th>Scan</th>
                  <th>Ranked</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const summary = row.summary as Record<string, number | undefined> | undefined;
                  const active = row.id === selectedRunId;
                  const scan =
                    row.scan_kind ??
                    (typeof row.config === "object" && row.config
                      ? String((row.config as Record<string, unknown>).scan_kind ?? "—")
                      : "—");
                  return (
                    <tr key={row.id} className={active ? "bg-accent/10" : undefined}>
                      <td className="text-muted whitespace-nowrap">
                        {row.finished_at_utc ? formatUtcTimestamp(row.finished_at_utc) : "—"}
                      </td>
                      <td>{row.exchange}</td>
                      <td className="text-xs text-muted">{scan}</td>
                      <td>{summary?.candidates_evaluated ?? "—"}</td>
                      <td>
                        <Button
                          type="button"
                          variant={active ? "primary" : "secondary"}
                          className="!py-1 !px-2 text-xs"
                          onClick={() => onSelectRun(active ? null : row.id, row.job_id)}
                        >
                          {active ? "Hide" : "View"}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {selected && (dbRunQuery.isLoading || artifactReportQuery.isLoading) && !report && (
        <Skeleton className="h-40 w-full" />
      )}
      {selected && !report && (dbRunQuery.error || artifactReportQuery.error) && (
        <p className="text-sm text-amber-200/90">Could not load report for this run.</p>
      )}
      {selected && report && (
        <Card title="Historical rankings" description={`Run ${selected.id.slice(0, 8)}…`}>
          <DiscoveryRunConfigSummary report={report} />
          <DiscoveryMacroCards report={report} />
          <DiscoverySummaryStats summary={report.summary} />
          <DiscoverySentimentSnippet report={report} />
          <DiscoveryMarketStructureSnippet report={report} />
          <DiscoveryScreenerPresetTable report={report} />
          <DiscoveryTrendScannerTable report={report} />
          <DiscoveryRankingsBlock report={report} highlightSymbols={highlightSymbols} />
        </Card>
      )}
    </div>
  );
}
