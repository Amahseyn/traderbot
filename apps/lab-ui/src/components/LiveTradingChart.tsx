"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { api, type OhlcBar } from "@/lib/api";
import { summarizeLiveJobLog, type TradeMarker } from "@/lib/liveLog";
import { formatMoney, formatResolutionLabel, formatUtcTimestamp } from "@/lib/format";

type LiveTradingChartProps = {
  jobId: string;
  src: string;
  dst: string;
  interval: string;
  symbol: string | null;
  logText: string;
  refreshActive: boolean;
  jobStatus?: string;
  strategyId?: string | null;
  liveOrders?: boolean;
  title: string;
  subtitle?: string;
  focused?: boolean;
  onFocus?: () => void;
  onDismiss?: () => void;
};

const CHART_HEIGHT = 300;
const PADDING = { top: 20, right: 64, bottom: 36, left: 12 };

function barIndexForTimestamp(bars: OhlcBar[], timestamp: number): number {
  let index = bars.findIndex((bar) => Number(bar.timestamp) === timestamp);
  if (index >= 0) {
    return index;
  }
  let best = -1;
  let bestDelta = Number.POSITIVE_INFINITY;
  for (let barIndex = 0; barIndex < bars.length; barIndex += 1) {
    const delta = Math.abs(Number(bars[barIndex].timestamp) - timestamp);
    if (delta < bestDelta) {
      bestDelta = delta;
      best = barIndex;
    }
  }
  return best;
}

function formatAxisPrice(value: number, dst: string): string {
  const quote = dst.trim().toLowerCase();
  if (quote === "usdt") {
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(2)}M`;
  }
  if (value >= 10_000) {
    return `${(value / 1_000).toFixed(1)}k`;
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

function formatBarTime(timestamp: number): string {
  const date = new Date(timestamp * 1000);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function LiveTradingChart({
  jobId,
  src,
  dst,
  interval,
  symbol,
  logText,
  refreshActive,
  jobStatus,
  strategyId,
  liveOrders,
  title,
  subtitle,
  focused,
  onFocus,
  onDismiss,
}: LiveTradingChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [chartWidth, setChartWidth] = useState(640);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) {
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width ?? 640;
      setChartWidth(Math.max(280, Math.floor(width)));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const ohlcQuery = useQuery({
    queryKey: ["markets-ohlc", src, dst, interval],
    queryFn: () => api.marketsOhlc({ src, dst, resolution: interval, maxBars: 300 }),
    enabled: Boolean(src && dst && interval),
    staleTime: 10_000,
    refetchInterval: refreshActive ? 15_000 : 90_000,
  });

  const summary = useMemo(() => summarizeLiveJobLog(logText), [logText]);
  const bars = ohlcQuery.data?.bars ?? [];

  const lastBar = bars.length > 0 ? bars[bars.length - 1] : null;
  const prevBar = bars.length > 1 ? bars[bars.length - 2] : null;
  const lastClose = lastBar ? Number(lastBar.close) : null;
  const prevClose = prevBar ? Number(prevBar.close) : null;
  const changePct =
    lastClose != null && prevClose != null && prevClose !== 0
      ? ((lastClose - prevClose) / prevClose) * 100
      : null;

  const plot = useMemo(() => {
    if (bars.length < 2) {
      return null;
    }
    const innerWidth = chartWidth - PADDING.left - PADDING.right;
    const innerHeight = CHART_HEIGHT - PADDING.top - PADDING.bottom;
    const lows = bars.map((bar) => Number(bar.low));
    const highs = bars.map((bar) => Number(bar.high));
    const minPrice = Math.min(...lows);
    const maxPrice = Math.max(...highs);
    const padding = (maxPrice - minPrice) * 0.06 || maxPrice * 0.01 || 1;
    const yMin = minPrice - padding;
    const yMax = maxPrice + padding;
    const span = yMax - yMin || 1;
    const yFor = (price: number) =>
      PADDING.top + innerHeight - ((price - yMin) / span) * innerHeight;
    const candleWidth = innerWidth / bars.length;
    const bodyWidth = Math.max(2, candleWidth * 0.62);

    const yTicks = [0, 0.25, 0.5, 0.75, 1].map((fraction) => {
      const price = yMin + span * (1 - fraction);
      return { price, y: PADDING.top + innerHeight * fraction };
    });

    const candles = bars.map((bar, index) => {
      const open = Number(bar.open);
      const close = Number(bar.close);
      const high = Number(bar.high);
      const low = Number(bar.low);
      const xCenter = PADDING.left + index * candleWidth + candleWidth / 2;
      const bullish = close >= open;
      return {
        index,
        xCenter,
        xLeft: PADDING.left + index * candleWidth,
        width: candleWidth,
        yHigh: yFor(high),
        yLow: yFor(low),
        yOpen: yFor(open),
        yClose: yFor(close),
        bodyWidth,
        bullish,
        open,
        close,
        high,
        low,
        timestamp: Number(bar.timestamp),
      };
    });

    const markers: Array<TradeMarker & { x: number; y: number }> = [];
    for (const marker of summary.markers) {
      const index = barIndexForTimestamp(bars, marker.timestamp);
      if (index < 0) {
        continue;
      }
      const candle = candles[index];
      markers.push({
        ...marker,
        x: candle.xCenter,
        y: marker.action === "buy" ? candle.yLow + 12 : candle.yHigh - 12,
      });
    }

    const xLabelIndexes = [0, Math.floor(bars.length / 2), bars.length - 1].filter(
      (value, index, array) => array.indexOf(value) === index,
    );

    return { candles, markers, yTicks, yMin, yMax, xLabelIndexes, innerHeight };
  }, [bars, summary.markers, chartWidth]);

  function handlePointerMove(clientX: number) {
    if (!plot || !containerRef.current) {
      return;
    }
    const rect = containerRef.current.getBoundingClientRect();
    const relativeX = clientX - rect.left;
    const scale = chartWidth / rect.width;
    const svgX = relativeX * scale;
    const index = plot.candles.findIndex(
      (candle) => svgX >= candle.xLeft && svgX < candle.xLeft + candle.width,
    );
    setHoverIndex(index >= 0 ? index : null);
  }

  const hoverCandle = hoverIndex != null && plot ? plot.candles[hoverIndex] : null;

  return (
    <article
      className={`overflow-hidden rounded-2xl border bg-gradient-to-b from-slate-900/80 to-panel shadow-lg transition ring-1 ${
        focused ? "border-accent/50 ring-accent/30" : "border-border ring-border/80"
      }`}
      onClick={() => onFocus?.()}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          onFocus?.();
        }
      }}
      role="button"
      tabIndex={0}
      aria-label={`Chart for ${title}`}
    >
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border/80 px-4 py-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate text-base font-semibold text-white">{title}</h3>
            <span className="rounded-md bg-surface px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted ring-1 ring-border">
              {formatResolutionLabel(interval)}
            </span>
            {liveOrders ? (
              <span className="rounded-md bg-red-950/60 px-2 py-0.5 text-[10px] font-medium text-red-200 ring-1 ring-red-500/30">
                Live
              </span>
            ) : (
              <span className="rounded-md bg-emerald-950/50 px-2 py-0.5 text-[10px] font-medium text-emerald-200 ring-1 ring-emerald-500/25">
                Paper
              </span>
            )}
            {jobStatus && <StatusBadge status={jobStatus} />}
          </div>
          {subtitle && <p className="text-xs text-muted">{subtitle}</p>}
          {strategyId && (
            <p className="font-mono text-[10px] text-slate-500">
              job {jobId.slice(0, 8)} · {strategyId}
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1 text-right">
          <p className="text-2xl font-semibold tabular-nums text-white">
            {lastClose != null ? formatMoney(lastClose) : "—"}
            <span className="ml-1 text-sm font-normal text-muted">{dst.toUpperCase()}</span>
          </p>
          {changePct != null && (
            <p
              className={`text-xs font-medium tabular-nums ${
                changePct > 0 ? "text-emerald-400" : changePct < 0 ? "text-red-400" : "text-muted"
              }`}
            >
              {changePct > 0 ? "+" : ""}
              {changePct.toFixed(2)}% vs prev candle
            </p>
          )}
          <div className="flex gap-2">
            {onFocus && (
              <Button
                type="button"
                variant="ghost"
                className="text-xs"
                onClick={(event) => {
                  event.stopPropagation();
                  onFocus();
                }}
              >
                View log
              </Button>
            )}
            {onDismiss && (
              <Button
                type="button"
                variant="ghost"
                className="text-xs text-muted"
                onClick={(event) => {
                  event.stopPropagation();
                  onDismiss();
                }}
              >
                Hide chart
              </Button>
            )}
          </div>
        </div>
      </header>

      {summary.paperWallet && (
        <div className="grid grid-cols-2 gap-2 border-b border-border/60 bg-surface/40 px-4 py-2 text-xs sm:grid-cols-4">
          <div>
            <p className="text-muted">Cash</p>
            <p className="font-medium text-slate-100">
              {formatMoney(summary.paperWallet.quote_cash)} {summary.paperWallet.quote_currency}
            </p>
          </div>
          <div>
            <p className="text-muted">Base</p>
            <p className="font-medium text-slate-100">{formatMoney(summary.paperWallet.base_amount)}</p>
          </div>
          <div>
            <p className="text-muted">Equity</p>
            <p className="font-medium text-emerald-300">{formatMoney(summary.paperWallet.equity)}</p>
          </div>
          <div>
            <p className="text-muted">Mark</p>
            <p className="font-medium text-slate-100">{formatMoney(summary.paperWallet.mark_price)}</p>
          </div>
        </div>
      )}

      <div className="px-3 py-3">
        {ohlcQuery.isLoading && <p className="text-sm text-muted">Loading candles…</p>}
        {ohlcQuery.isError && (
          <p className="text-sm text-red-400">Could not load OHLC for this session.</p>
        )}

        {plot && (
          <div
            ref={containerRef}
            className="relative w-full"
            onMouseMove={(event) => handlePointerMove(event.clientX)}
            onMouseLeave={() => setHoverIndex(null)}
          >
            <svg
              viewBox={`0 0 ${chartWidth} ${CHART_HEIGHT}`}
              className="w-full rounded-xl border border-border/60 bg-surface/90"
              role="img"
              aria-label={`Candlestick chart for ${symbol ?? title}`}
            >
              <defs>
                <linearGradient id={`grid-fade-${jobId}`} x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#1e293b" stopOpacity="0.35" />
                  <stop offset="100%" stopColor="#0f172a" stopOpacity="0.1" />
                </linearGradient>
              </defs>
              <rect
                x={PADDING.left}
                y={PADDING.top}
                width={chartWidth - PADDING.left - PADDING.right}
                height={CHART_HEIGHT - PADDING.top - PADDING.bottom}
                fill={`url(#grid-fade-${jobId})`}
              />
              {plot.yTicks.map((tick) => (
                <g key={tick.price}>
                  <line
                    x1={PADDING.left}
                    x2={chartWidth - PADDING.right}
                    y1={tick.y}
                    y2={tick.y}
                    stroke="#334155"
                    strokeDasharray="4 6"
                    strokeOpacity={0.65}
                  />
                  <text
                    x={chartWidth - PADDING.right + 6}
                    y={tick.y + 4}
                    fill="#94a3b8"
                    fontSize={10}
                    fontFamily="ui-monospace, monospace"
                  >
                    {formatAxisPrice(tick.price, dst)}
                  </text>
                </g>
              ))}
              {plot.candles.map((candle) => (
                <g key={candle.timestamp}>
                  <line
                    x1={candle.xCenter}
                    x2={candle.xCenter}
                    y1={candle.yHigh}
                    y2={candle.yLow}
                    stroke={candle.bullish ? "#34d399" : "#f87171"}
                    strokeWidth={1.2}
                    opacity={hoverIndex === candle.index || hoverIndex === null ? 1 : 0.45}
                  />
                  <rect
                    x={candle.xCenter - candle.bodyWidth / 2}
                    y={Math.min(candle.yOpen, candle.yClose)}
                    width={candle.bodyWidth}
                    height={Math.max(2, Math.abs(candle.yClose - candle.yOpen))}
                    fill={candle.bullish ? "#34d399" : "#f87171"}
                    opacity={hoverIndex === candle.index || hoverIndex === null ? 1 : 0.45}
                  />
                </g>
              ))}
              {hoverCandle && (
                <line
                  x1={hoverCandle.xCenter}
                  x2={hoverCandle.xCenter}
                  y1={PADDING.top}
                  y2={CHART_HEIGHT - PADDING.bottom}
                  stroke="#64748b"
                  strokeDasharray="3 4"
                />
              )}
              {plot.markers.map((marker, index) => (
                <g key={`${marker.timestamp}-${marker.action}-${index}`}>
                  <circle
                    cx={marker.x}
                    cy={marker.y}
                    r={9}
                    fill={marker.action === "buy" ? "#14532d" : "#450a0a"}
                    stroke={marker.action === "buy" ? "#4ade80" : "#f87171"}
                    strokeWidth={1.5}
                  />
                  <text
                    x={marker.x}
                    y={marker.y + 4}
                    textAnchor="middle"
                    fill={marker.action === "buy" ? "#bbf7d0" : "#fecaca"}
                    fontSize={9}
                    fontWeight="bold"
                  >
                    {marker.action === "buy" ? "B" : "S"}
                  </text>
                  <title>
                    {marker.action.toUpperCase()} @ {marker.price} ({marker.mode ?? "—"})
                  </title>
                </g>
              ))}
              {plot.xLabelIndexes.map((barIndex) => {
                const candle = plot.candles[barIndex];
                if (!candle) {
                  return null;
                }
                return (
                  <text
                    key={candle.timestamp}
                    x={candle.xCenter}
                    y={CHART_HEIGHT - 8}
                    textAnchor="middle"
                    fill="#64748b"
                    fontSize={9}
                  >
                    {formatBarTime(candle.timestamp)}
                  </text>
                );
              })}
            </svg>

            {hoverCandle && (
              <div
                className="pointer-events-none absolute left-3 top-3 rounded-lg border border-border bg-slate-950/90 px-3 py-2 text-xs shadow-xl backdrop-blur-sm"
              >
                <p className="font-medium text-white">{formatBarTime(hoverCandle.timestamp)}</p>
                <p className="text-muted">
                  O {formatMoney(hoverCandle.open)} · H {formatMoney(hoverCandle.high)}
                </p>
                <p className="text-muted">
                  L {formatMoney(hoverCandle.low)} · C {formatMoney(hoverCandle.close)}
                </p>
              </div>
            )}
          </div>
        )}

        {!ohlcQuery.isLoading && bars.length < 2 && (
          <p className="text-sm text-muted">Not enough candle data to draw a chart yet.</p>
        )}

        <footer className="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-muted">
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-sm bg-emerald-400" /> Up
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-sm bg-red-400" /> Down
          </span>
          <span>{summary.markers.length} trades in log</span>
          {refreshActive && (
            <span className="text-emerald-400/90">Refreshing while session runs</span>
          )}
          {ohlcQuery.dataUpdatedAt > 0 && (
            <span>
              Candles updated {formatUtcTimestamp(new Date(ohlcQuery.dataUpdatedAt).toISOString())}
            </span>
          )}
        </footer>
      </div>
    </article>
  );
}
