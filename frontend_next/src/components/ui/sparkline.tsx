"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Tiny inline SVG line chart. No dependencies, no axes, no labels.
 *
 *   <Sparkline data={[1, 4, 2, 8, 5, 9, 7]} />
 *
 * Designed to sit next to a KPI number — the visual is the *shape*,
 * not specific values. For a richer line chart with axes use the
 * `<LineChart>` primitive (next door).
 */
export interface SparklineProps extends React.HTMLAttributes<HTMLDivElement> {
  data: number[];
  width?: number;
  height?: number;
  /** Fill the area under the line with a soft tint of the same color. */
  fill?: boolean;
  /** Override the line color. Defaults to currentColor so it inherits
   *  from the parent's `text-*` class. */
  stroke?: string;
  strokeWidth?: number;
}

export function Sparkline({
  data,
  width = 96,
  height = 28,
  fill = true,
  stroke,
  strokeWidth = 1.5,
  className,
  ...divProps
}: SparklineProps) {
  // Guard: a sparkline with 0 or 1 point isn't meaningful — render a flat
  // muted line so the card layout stays consistent.
  const points = data.length >= 2 ? data : [...data, ...data];
  const max = Math.max(...points, 1);
  const min = Math.min(...points, 0);
  const range = max - min || 1;
  const step = width / Math.max(points.length - 1, 1);
  const padY = strokeWidth + 1;
  const innerH = height - padY * 2;

  const coords = points.map((v, i) => {
    const x = i * step;
    const y = padY + (1 - (v - min) / range) * innerH;
    return [x, y] as const;
  });

  const linePath = coords
    .map(([x, y], i) => (i === 0 ? `M${x.toFixed(2)},${y.toFixed(2)}` : `L${x.toFixed(2)},${y.toFixed(2)}`))
    .join(" ");

  const areaPath =
    `${linePath} L${(width).toFixed(2)},${(height).toFixed(2)} ` +
    `L0,${(height).toFixed(2)} Z`;

  return (
    <div
      aria-hidden
      className={cn("inline-block text-primary", className)}
      {...divProps}
    >
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        role="img"
      >
        {fill && (
          <path
            d={areaPath}
            fill={stroke ?? "currentColor"}
            fillOpacity={0.08}
          />
        )}
        <path
          d={linePath}
          fill="none"
          stroke={stroke ?? "currentColor"}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

/**
 * A bigger line chart with X labels at each end and a hover-friendly
 * grid line. Same SVG approach as Sparkline, just sized up.
 */
export interface LineChartProps {
  data: { date: string; count: number }[];
  height?: number;
  className?: string;
}

export function LineChart({ data, height = 220, className }: LineChartProps) {
  const [width, setWidth] = React.useState(640);
  const wrapRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!wrapRef.current) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) setWidth(Math.max(280, Math.floor(w)));
    });
    ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, []);

  if (data.length === 0) {
    return (
      <div
        ref={wrapRef}
        style={{ height }}
        className={cn(
          "flex items-center justify-center text-xs text-muted-foreground",
          className
        )}
      >
        No activity in this period.
      </div>
    );
  }

  const padX = 28;
  const padTop = 12;
  const padBottom = 24;
  const innerW = width - padX * 2;
  const innerH = height - padTop - padBottom;
  const max = Math.max(...data.map((d) => d.count), 1);
  const stepX = innerW / Math.max(data.length - 1, 1);

  const coords = data.map((d, i) => {
    const x = padX + i * stepX;
    const y = padTop + (1 - d.count / max) * innerH;
    return [x, y, d] as const;
  });

  const linePath = coords
    .map(([x, y], i) => (i === 0 ? `M${x.toFixed(2)},${y.toFixed(2)}` : `L${x.toFixed(2)},${y.toFixed(2)}`))
    .join(" ");
  const areaPath =
    `${linePath} L${(padX + innerW).toFixed(2)},${(padTop + innerH).toFixed(2)} ` +
    `L${padX},${(padTop + innerH).toFixed(2)} Z`;

  // Four horizontal grid lines: 0, ¼, ½, ¾, max.
  const gridY = [0, 0.25, 0.5, 0.75, 1].map((p) => padTop + p * innerH);

  return (
    <div ref={wrapRef} className={className}>
      <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`}>
        {gridY.map((y, i) => (
          <line
            key={i}
            x1={padX}
            x2={padX + innerW}
            y1={y}
            y2={y}
            stroke="currentColor"
            strokeOpacity={0.08}
            className="text-foreground"
          />
        ))}
        <path d={areaPath} fill="currentColor" fillOpacity={0.08} className="text-primary" />
        <path
          d={linePath}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="text-primary"
        />
        {coords.map(([x, y, d], i) => (
          <circle
            key={i}
            cx={x}
            cy={y}
            r={2.5}
            fill="currentColor"
            className="text-primary"
          >
            <title>{`${d.date}: ${d.count}`}</title>
          </circle>
        ))}
        {/* X-axis labels: first and last date only, to keep things calm */}
        <text
          x={padX}
          y={height - 6}
          fontSize={10}
          fill="currentColor"
          className="text-muted-foreground"
        >
          {data[0]?.date.slice(5)}
        </text>
        <text
          x={padX + innerW}
          y={height - 6}
          fontSize={10}
          textAnchor="end"
          fill="currentColor"
          className="text-muted-foreground"
        >
          {data[data.length - 1]?.date.slice(5)}
        </text>
      </svg>
    </div>
  );
}
