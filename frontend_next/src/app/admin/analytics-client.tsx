"use client";

import { useQuery } from "@tanstack/react-query";
import { Users, FileText, Cpu, Activity } from "lucide-react";
import { api } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function AdminAnalyticsClient() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-analytics"],
    queryFn: api.adminGetAnalytics,
  });

  if (isLoading) return <Skeleton className="h-32 w-full" />;
  if (!data) return null;
  const m = data.metrics;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat
          icon={<Users className="h-4 w-4" />}
          label="Total users"
          value={Number(m.total_users || 0)}
        />
        <Stat
          icon={<Activity className="h-4 w-4 text-success" />}
          label="Active today"
          value={Number(m.active_today || m.active_users || 0)}
        />
        <Stat
          icon={<FileText className="h-4 w-4" />}
          label="PDFs uploaded"
          value={Number(m.total_pdfs || 0)}
        />
        <Stat
          icon={<Cpu className="h-4 w-4" />}
          label="AI API calls"
          value={Number(m.total_ai_calls || 0)}
        />
      </div>

      {data.usage_over_time && data.usage_over_time.length > 0 && (
        <Card>
          <CardContent className="p-5">
            <h3 className="mb-3 text-sm font-semibold">Activity (last 7 days)</h3>
            <UsageBars rows={data.usage_over_time} />
          </CardContent>
        </Card>
      )}

      {data.feature_usage && Object.keys(data.feature_usage).length > 0 && (
        <Card>
          <CardContent className="p-5">
            <h3 className="mb-3 text-sm font-semibold">Feature usage</h3>
            <FeatureBars usage={data.feature_usage} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {icon} {label}
        </div>
        <div className="mt-1 text-2xl font-bold">{value.toLocaleString()}</div>
      </CardContent>
    </Card>
  );
}

function UsageBars({ rows }: { rows: { date: string; count: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div className="flex items-end gap-2">
      {rows.map((r) => (
        <div key={r.date} className="flex flex-1 flex-col items-center gap-1">
          <div
            className="w-full rounded-t bg-primary"
            style={{ height: `${(r.count / max) * 120}px`, minHeight: "4px" }}
            title={`${r.count} actions`}
          />
          <span className="text-[10px] text-muted-foreground">
            {r.date.slice(5)}
          </span>
        </div>
      ))}
    </div>
  );
}

function FeatureBars({ usage }: { usage: Record<string, number> }) {
  const entries = Object.entries(usage).sort(([, a], [, b]) => b - a);
  const max = Math.max(1, ...entries.map(([, c]) => c));
  return (
    <div className="space-y-1.5">
      {entries.map(([name, count]) => (
        <div key={name} className="text-xs">
          <div className="flex justify-between">
            <span>{name}</span>
            <span className="text-muted-foreground">{count}</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-3">
            <div
              className="h-full bg-primary"
              style={{ width: `${(count / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
