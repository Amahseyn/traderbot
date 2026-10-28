"use client";

import { useMemo } from "react";

interface SparklineChartProps {
  data: number[];
  change?: number | null;
  width?: number;
  height?: number;
  className?: string;
}

export function SparklineChart({
  data,
  change,
  width = 120,
  height = 36,
  className = "",
}: SparklineChartProps) {
  const { pathD, isPositive } = useMemo(() => {
    if (!data || data.length < 2) {
      return { pathD: "", isPositive: true };
    }

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;
    const padding = 2;
    const availableHeight = height - padding * 2;
    const stepX = width / (data.length - 1);

    const points = data.map((val, index) => {
      const x = index * stepX;
      // Invert Y because SVG coordinates origin is top-left
      const y = height - padding - ((val - min) / range) * availableHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });

    const isPos =
      change !== undefined && change !== null
        ? change >= 0
        : data[data.length - 1] >= data[0];

    return {
      pathD: `M ${points.join(" L ")}`,
      isPositive: isPos,
    };
  }, [data, change, width, height]);

  if (!pathD) {
    return (
      <div
        className={`flex items-center justify-center text-[10px] text-muted ${className}`}
        style={{ width, height }}
      >
        —
      </div>
    );
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={`shrink-0 overflow-visible ${className}`}
      aria-hidden="true"
    >
      <path
        d={pathD}
        fill="none"
        stroke={isPositive ? "#10b981" : "#f43f5e"}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
