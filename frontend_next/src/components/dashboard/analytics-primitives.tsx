"use client";

import * as React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Sparkline } from "@/components/ui/sparkline";
import { cn } from "@/lib/utils";

/**
 * Shared primitives for the role-scoped analytics pages.
 *
 * Both the admin's `/admin` analytics (cross-tenant view) and the
 * teacher's `/teacher` home dashboard (personal view) render the same
 * shape — KPI tiles + a line chart + a bar list — so the visual
 * language stays consistent across roles. Pulling them out of
 * `admin/analytics-client.tsx` removes one source of accidental drift.
 */

// ── KPI tile ──────────────────────────────────────────────────────────

export function KpiCard({
  icon,
  label,
  value,
  accent,
  loading,
  sparkline,
}: {
  icon: React.ReactNode;
  label: string;
  /** When `undefined`, the tile renders 0 (handles the in-flight
   *  React Query state where data hasn't loaded yet but loading=false). */
  value: number | undefined;
  /** Tint the label in `text-success` — used for the "active users"
   *  tile so the most engagement-relevant metric stands out. */
  accent?: boolean;
  loading?: boolean;
  /** Optional inline sparkline next to the number (admin uses this for
   *  the active-users and AI-calls tiles). */
  sparkline?: number[];
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div
          className={cn(
            "flex items-center gap-2 text-xs",
            accent ? "text-success" : "text-muted-foreground"
          )}
        >
          {icon}
          {label}
        </div>
        <div className="mt-1 flex items-end justify-between gap-2">
          <div className="text-2xl font-bold tracking-tight tabular-nums">
            {loading ? (
              <Skeleton className="h-7 w-16" />
            ) : (
              (value ?? 0).toLocaleString()
            )}
          </div>
          {!loading && sparkline && sparkline.length > 1 && (
            <Sparkline data={sparkline} className="text-primary" />
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Feature usage bars ────────────────────────────────────────────────

export function FeatureBars({
  usage,
  labels = {},
}: {
  usage: Record<string, number>;
  /** Optional friendly-name overrides ("qa" → "Q&A", "fill_in_blank" →
   *  "Fill in blank"). Anything not mapped renders as the raw key. */
  labels?: Record<string, string>;
}) {
  const entries = Object.entries(usage).sort(([, a], [, b]) => b - a);
  if (entries.length === 0) {
    return (
      <p className="py-6 text-center text-xs text-muted-foreground">
        No feature usage recorded yet.
      </p>
    );
  }
  const max = Math.max(1, ...entries.map(([, c]) => c));
  return (
    <div className="space-y-2.5">
      {entries.map(([name, count]) => {
        const pct = (count / max) * 100;
        return (
          <div key={name} className="text-xs">
            <div className="mb-1 flex justify-between">
              <span className="font-medium">{labels[name] ?? name}</span>
              <span className="tabular-nums text-muted-foreground">
                {count.toLocaleString()}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Period selector tabs ──────────────────────────────────────────────

export type AnalyticsPeriodValue = "1d" | "7d" | "30d" | "90d";

export function AnalyticsPeriodTabs<T extends string>({
  value,
  onChange,
  periods,
  ariaLabel = "Time period",
}: {
  value: T;
  onChange: (next: T) => void;
  periods: { value: T; label: string }[];
  ariaLabel?: string;
}) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="inline-flex items-center rounded-md border border-border bg-surface p-0.5"
    >
      {periods.map((p) => (
        <button
          key={p.value}
          role="tab"
          aria-selected={value === p.value}
          onClick={() => onChange(p.value)}
          className={cn(
            "rounded-sm px-3 py-1 text-xs font-medium transition-colors",
            value === p.value
              ? "bg-primary-chip text-primary"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
