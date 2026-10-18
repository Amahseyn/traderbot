"use client";

import { useMutation } from "@tanstack/react-query";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { api } from "@/lib/api";

type TrendItem = {
  symbol?: string;
  price?: number;
  scores?: Record<string, { score?: number; direction?: string }>;
};

type DiscoveryTrendPreviewProps = {
  exchange: string;
  trendSort: string;
  trendDir: string;
  trendQuote: string;
  disabled?: boolean;
};

function scoreForSort(item: TrendItem, sort: string): number | null {
  const bucket = item.scores?.[sort];
  return bucket?.score ?? null;
}

export function DiscoveryTrendPreview({
  exchange,
  trendSort,
  trendDir,
  trendQuote,
  disabled,
}: DiscoveryTrendPreviewProps) {
  const previewMutation = useMutation({
    mutationFn: () =>
      api.coinbeaconTrendScanner({
        exchange,
        sort: trendSort,
        dir: trendDir,
        quote: trendQuote,
      }),
  });

  const payload = previewMutation.data;
  const items = Array.isArray(payload?.items) ? (payload.items as TrendItem[]) : [];

  return (
    <Card
      title="Trend board preview"
      description="Optional live snapshot via GET /api/coinbeacon/trend-scanner (~5 credits). Full discovery still runs screeners + merge."
    >
      <Button
        type="button"
        variant="secondary"
        disabled={disabled || previewMutation.isPending}
        onClick={() => previewMutation.mutate()}
      >
        {previewMutation.isPending ? "Loading…" : "Load trend board"}
      </Button>
      {previewMutation.error && (
        <p className="mt-2 text-sm text-red-200/90">{String(previewMutation.error)}</p>
      )}
      {items.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="data w-full text-sm">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Price</th>
                <th>Trend ({trendSort})</th>
              </tr>
            </thead>
            <tbody>
              {items.slice(0, 15).map((row, index) => (
                <tr key={row.symbol ?? `row-${index}`}>
                  <td className="font-mono text-xs">{row.symbol ?? "—"}</td>
                  <td>{row.price != null ? row.price.toLocaleString() : "—"}</td>
                  <td>{scoreForSort(row, trendSort) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {items.length > 15 && (
            <p className="mt-1 text-xs text-muted">Showing 15 of {items.length} (total {String(payload?.total ?? items.length)})</p>
          )}
        </div>
      )}
    </Card>
  );
}
