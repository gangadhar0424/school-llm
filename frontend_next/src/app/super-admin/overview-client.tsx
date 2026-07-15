"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Building2,
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

export function SuperAdminOverviewClient() {
  const [period, setPeriod] = React.useState<AnalyticsPeriod>("7d");

  const analytics = useQuery({
    queryKey: ["super-admin-analytics", period],
    queryFn: () => api.superAdminAnalytics(period),
  });
  const overview = useQuery({
    queryKey: ["super-admin-overview"],
    queryFn: api.superAdminOverview,
  });

  const usage = analytics.data?.usage_over_time ?? [];
  const featureUsage = analytics.data?.feature_usage ?? {};
  const isLoading = analytics.isLoading || overview.isLoading;

  return (
    <div className="space-y-6">
      {/* Period + refresh */}
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

        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            analytics.refetch();
            overview.refetch();
          }}
          disabled={analytics.isFetching || overview.isFetching}
        >
          <RefreshCw
            className={cn(
              "h-3.5 w-3.5",
              (analytics.isFetching || overview.isFetching) && "animate-spin"
            )}
          />
          Refresh
        </Button>
      </div>

      {/* Top KPI row — platform-only metric (schools) + rest of standard KPIs */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <KpiCard
          icon={<Building2 className="h-4 w-4" />}
          label="Schools"
          value={Number(overview.data?.schools_count ?? 0)}
          loading={isLoading}
        />
        <KpiCard
          icon={<Users className="h-4 w-4" />}
          label="Total users"
          value={Number(analytics.data?.metrics?.total_users ?? 0)}
          loading={isLoading}
        />
        <KpiCard
          icon={<Activity className="h-4 w-4" />}
          label="Active"
          value={Number(
            analytics.data?.metrics?.active_today ??
              analytics.data?.metrics?.active_users ??
              0
          )}
          accent
          loading={isLoading}
          sparkline={usage.map((u) => u.count)}
        />
        <KpiCard
          icon={<FileText className="h-4 w-4" />}
          label="PDFs uploaded"
          value={Number(analytics.data?.metrics?.total_pdfs ?? 0)}
          loading={isLoading}
        />
        <KpiCard
          icon={<Cpu className="h-4 w-4" />}
          label="AI API calls"
          value={Number(analytics.data?.metrics?.total_ai_calls ?? 0)}
          loading={isLoading}
          sparkline={usage.map((u) => u.count)}
        />
      </div>

      {/* Activity over time */}
      <Card>
        <CardContent className="p-5">
          <div className="mb-1">
            <h3 className="text-sm font-semibold">Activity over time</h3>
            <p className="text-xs text-muted-foreground">
              Total actions per day across all schools.
            </p>
          </div>
          {analytics.isLoading ? (
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
                All-time count of each AI feature invocation, across every
                school.
              </p>
            </div>
            {!analytics.isLoading && (
              <span className="text-xs text-muted-foreground">
                {Object.values(featureUsage).reduce((a, b) => a + b, 0)} total
              </span>
            )}
          </div>
          {analytics.isLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : (
            <FeatureBars usage={featureUsage} labels={FEATURE_LABEL} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
