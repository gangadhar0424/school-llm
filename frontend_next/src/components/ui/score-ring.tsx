import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Circular progress ring used as a visual headline for percentage
 * scores (AI eval avg, quiz attempts, assignment grades, etc).
 *
 *   <ScoreRing value={73} />
 *
 * Pure SVG, no deps. Color-codes by band:
 *   ≥ 80%  → success
 *   ≥ 50%  → warning
 *   < 50%  → danger
 *
 * Sizing is driven by the `size` prop (pixel diameter, defaults to 80).
 */
export interface ScoreRingProps {
  /** Value as a percentage, 0..100. Clamped on render. */
  value: number;
  size?: number;
  /** Stroke thickness. Defaults to ~10% of size. */
  strokeWidth?: number;
  /** Optional label rendered above the percentage (e.g. "Avg score"). */
  label?: string;
  /** Force a specific color band — overrides the automatic mapping. */
  tone?: "success" | "warning" | "danger";
  className?: string;
}

export function ScoreRing({
  value,
  size = 80,
  strokeWidth,
  label,
  tone,
  className,
}: ScoreRingProps) {
  const clamped = Math.max(0, Math.min(100, value));
  const sw = strokeWidth ?? Math.max(4, Math.round(size * 0.1));
  const r = (size - sw) / 2;
  const c = 2 * Math.PI * r;
  const dash = (clamped / 100) * c;

  const resolvedTone: "success" | "warning" | "danger" =
    tone ??
    (clamped >= 80 ? "success" : clamped >= 50 ? "warning" : "danger");

  const toneColor: Record<typeof resolvedTone, string> = {
    success: "var(--success)",
    warning: "var(--warning)",
    danger: "var(--danger)",
  };

  return (
    <div
      className={cn("inline-flex flex-col items-center gap-1", className)}
      style={{ width: size }}
    >
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {/* Track */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--muted)"
            strokeWidth={sw}
          />
          {/* Progress */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={toneColor[resolvedTone]}
            strokeWidth={sw}
            strokeDasharray={`${dash} ${c}`}
            strokeLinecap="round"
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span
            className="text-base font-semibold tabular-nums tracking-tight"
            style={{ color: toneColor[resolvedTone] }}
          >
            {Math.round(clamped)}
            <span className="text-xs">%</span>
          </span>
        </div>
      </div>
      {label && (
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
      )}
    </div>
  );
}
