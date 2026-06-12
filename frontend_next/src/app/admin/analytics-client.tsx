"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Cpu,
  FileText,
  RefreshCw,
  Users,
} from "lucide-react";
import { api } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { LineChart } from "@/components/ui/sparkline";
import {
  FeatureBars,
  KpiCard,
} from "@/components/dashboard/analytics-primitives";
import { ExportButton } from "@/components/admin/export-button";
import type { ExportColumn } from "@/lib/csv-export";
import { useCurrentUser } from "@/lib/use-current-user";
import { cn } from "@/lib/utils";
import type { AnalyticsPeriod } from "@/lib/types";

const PERIODS: { value: AnalyticsPeriod; label: string }[] = [
  { value: "1d", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
  { value: "90d", label: "90d" },
];

const FEATURE_LABEL: Record<string, string> = {
  qa: "Q&A",
  quiz: "Quiz",
  summary: "Summary",
  audio: "Audio",
  video: "Video",
  pdf_upload: "PDF uploads",
  login: "Logins",
};

export function AdminAnalyticsClient() {
  const user = useCurrentUser();
  const [period, setPeriod] = React.useState<AnalyticsPeriod>("7d");
  const { data, isLoading, isFetching, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["admin-analytics", period],
    queryFn: () => api.adminGetAnalytics(period),
  });

  const usage = data?.usage_over_time ?? [];
  const featureUsage = data?.feature_usage ?? {};

  return (
    <div className="space-y-6">
      {/* Period selector + last refreshed */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div
          role="tablist"
          aria-label="Time period"
          className="inline-flex items-center rounded-md border border-border bg-surface p-0.5"
        >
          {PERIODS.map((p) => (
            <button
              key={p.value}
              role="tab"
              aria-selected={period === p.value}
              onClick={() => setPeriod(p.value)}
              className={cn(
                "rounded-sm px-3 py-1 text-xs font-medium transition-colors",
                period === p.value
                  ? "bg-primary-chip text-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          {dataUpdatedAt > 0 && (
            <span className="text-xs text-muted-foreground">
              Updated {formatAge(dataUpdatedAt)}
            </span>
          )}
          <Button
            size="sm"
            variant="outline"
            onClick={() => refetch()}
            disabled={isFetching}
          >
            <RefreshCw
              className={cn("h-3.5 w-3.5", isFetching && "animate-spin")}
            />
            Refresh
          </Button>
          <ExportButton
            label="Export"
            loading={isLoading}
            disabled={!data}
            options={() => {
              const preface: string[] = [
                `Period: ${period}`,
                "",
                "Metric summary",
                `Total users: ${data?.metrics?.total_users ?? 0}`,
                `Active users: ${data?.metrics?.active_users ?? data?.metrics?.active_today ?? 0}`,
                `PDFs uploaded: ${data?.metrics?.total_pdfs ?? 0}`,
                `AI API calls: ${data?.metrics?.total_ai_calls ?? 0}`,
                "",
                "Feature usage (all-time)",
                ...Object.entries(featureUsage).map(
                  ([k, v]) => `${FEATURE_LABEL[k] ?? k}: ${v}`
                ),
              ];
              const cols: ExportColumn<{ date: string; count: number }>[] = [
                { header: "Date", value: (r) => r.date },
                { header: "Actions", value: (r) => r.count },
              ];
              return {
                subject: "Analytics",
                schoolName: user?.school_name ?? null,
                filters: `period=${period}`,
                preface,
                columns: cols,
                rows: usage,
              };
            }}
          />
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          icon={<Users className="h-4 w-4" />}
          label="Total users"
          value={Number(data?.metrics?.total_users ?? 0)}
          loading={isLoading}
        />
        <KpiCard
          icon={<Activity className="h-4 w-4" />}
          label="Active"
          value={Number(
            data?.metrics?.active_today ?? data?.metrics?.active_users ?? 0
          )}
          accent
          loading={isLoading}
          sparkline={usage.map((u) => u.count)}
        />
        <KpiCard
          icon={<FileText className="h-4 w-4" />}
          label="PDFs uploaded"
          value={Number(data?.metrics?.total_pdfs ?? 0)}
          loading={isLoading}
        />
        <KpiCard
          icon={<Cpu className="h-4 w-4" />}
          label="AI API calls"
          value={Number(data?.metrics?.total_ai_calls ?? 0)}
          loading={isLoading}
          sparkline={usage.map((u) => u.count)}
        />
      </div>

      {/* Activity over time */}
      <Card>
        <CardContent className="p-5">
          <div className="mb-1 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold">Activity over time</h3>
              <p className="text-xs text-muted-foreground">
                Total actions per day in the selected period.
              </p>
            </div>
          </div>
          {isLoading ? (
            <Skeleton className="mt-3 h-48 w-full" />
          ) : (
            <LineChart data={usage} className="mt-3" />
          )}
        </CardContent>
      </Card>

      {/* Feature usage */}
      <Card>
        <CardContent className="p-5">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-sm font-semibold">Feature usage</h3>
              <p className="text-xs text-muted-foreground">
                All-time count of each AI feature invocation.
              </p>
            </div>
            {!isLoading && (
              <span className="text-xs text-muted-foreground">
                {Object.values(featureUsage).reduce((a, b) => a + b, 0)} total
              </span>
            )}
          </div>
          {isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : (
            <FeatureBars usage={featureUsage} labels={FEATURE_LABEL} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── helpers ─────────────────────────────────────────────────────────────

function formatAge(ts: number): string {
  const secs = Math.floor((Date.now() - ts) / 1000);
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)} min ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)} h ago`;
  return new Date(ts).toLocaleString();
}
