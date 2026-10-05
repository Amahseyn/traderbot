"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { ArtifactGallery } from "@/components/ArtifactGallery";
import { Card } from "@/components/ui/Card";
import { api, type EvaluationRun } from "@/lib/api";
import { formatReturnPct, parseReturnPct, returnPctClassName } from "@/lib/format";

type CompareSessionPanelProps = {
  sessionId: string;
  currentRunId: string;
  symbol: string | null;
};

export function CompareSessionPanel({ sessionId, currentRunId, symbol }: CompareSessionPanelProps) {
  const sessionsQuery = useQuery({
    queryKey: ["compare-sessions"],
    queryFn: () => api.compareSessions(),
  });
  const session = sessionsQuery.data?.find((row) => row.id === sessionId);

  const peersQuery = useQuery({
    queryKey: ["runs", "compare-peers", sessionId, symbol],
    enabled: Boolean(symbol),
    queryFn: async () => {
      const params = new URLSearchParams({
        run_kind: "strategy_backtest",
        limit: "500",
      });
      if (symbol) params.set("symbol", symbol);
      const runs = await api.runs(`?${params.toString()}`);
      return runs
        .filter((run) => run.compare_session_id === sessionId)
        .sort(
          (left, right) =>
            (parseReturnPct(right.metrics) ?? Number.NEGATIVE_INFINITY) -
            (parseReturnPct(left.metrics) ?? Number.NEGATIVE_INFINITY),
        );
    },
  });

  const peers = peersQuery.data ?? [];
  const rankByRunId = new Map(peers.map((run, index) => [run.id, index + 1]));

  return (
    <Card
      title="Strategy compare"
      description={
        session?.best_strategy_id
          ? `Best in this batch: ${session.best_strategy_id}`
          : "Other strategies tested on the same dataset in one compare job."
      }
    >
      {peersQuery.isLoading && <p className="text-muted text-sm">Loading compare results…</p>}
      {!peersQuery.isLoading && peers.length === 0 && (
        <p className="text-muted text-sm">No sibling runs found for this compare session.</p>
      )}
      {peers.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="data">
            <thead>
              <tr>
                <th>#</th>
                <th>Strategy</th>
                <th>Return</th>
                <th>Trades</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {peers.map((peer) => (
                <ComparePeerRow
                  key={peer.id}
                  peer={peer}
                  rank={rankByRunId.get(peer.id) ?? 0}
                  isCurrent={peer.id === currentRunId}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {(session?.artifacts?.length ?? 0) > 0 && (
        <div className="mt-6">
          <ArtifactGallery artifacts={session!.artifacts} title="Compare charts" />
        </div>
      )}
    </Card>
  );
}

function ComparePeerRow({
  peer,
  rank,
  isCurrent,
}: {
  peer: EvaluationRun;
  rank: number;
  isCurrent: boolean;
}) {
  const returnPct = parseReturnPct(peer.metrics);
  const trades = peer.metrics.trades;

  return (
    <tr className={isCurrent ? "bg-accent/5" : undefined}>
      <td className="text-muted">{rank}</td>
      <td className="font-medium text-white">{peer.strategy_id ?? "—"}</td>
      <td className={`font-mono text-sm ${returnPctClassName(returnPct)}`}>
        {formatReturnPct(returnPct)}
      </td>
      <td className="font-mono text-xs text-muted">
        {typeof trades === "number" ? trades : "—"}
      </td>
      <td className="text-right">
        {isCurrent ? (
          <span className="badge bg-accent/20 text-accent">This run</span>
        ) : (
          <Link href={`/runs/${peer.id}`} className="text-accent text-sm hover:underline">
            Open
          </Link>
        )}
      </td>
    </tr>
  );
}
