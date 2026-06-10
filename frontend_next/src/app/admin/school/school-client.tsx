"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BookOpen,
  GraduationCap,
  School,
  UserCheck,
  UserX,
} from "lucide-react";
import { api } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Sparkline } from "@/components/ui/sparkline";
import { EmptyState } from "@/components/ui/empty-state";
import { ExportButton } from "@/components/admin/export-button";
import type { ExportColumn } from "@/lib/csv-export";
import { useCurrentUser } from "@/lib/use-current-user";
import { cn } from "@/lib/utils";
import type { SchoolTopUser } from "@/lib/types";

/**
 * Admin "School" lobby — one API call, four stat tiles, two top-5 strips,
 * and a 14-day daily-active sparkline. No filters, no tables — those live
 * on the Teachers / Students drilldown pages (Phase 4 + 5).
 */
export function AdminSchoolClient() {
  const user = useCurrentUser();
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-school-overview"],
    queryFn: () => api.adminSchoolOverview(),
    // School-shape data is cached at the backend for 60s already; this
    // only controls the staleness on the client side. Refetch on focus
    // keeps the lobby fresh when an admin alt-tabs back to it.
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });

  const counts = data?.counts;
  const dau = data?.daily_active_14d ?? [];
  const dauSeries = dau.map((d) => d.count);
  // Tiny human-readable trend line under the sparkline: today vs the
  // 14-day average. Admins can tell at a glance if today is below par.
  const todayDau = dauSeries.length ? dauSeries[dauSeries.length - 1] : 0;
  const avgDau =
    dauSeries.length > 0
      ? Math.round(dauSeries.reduce((a, b) => a + b, 0) / dauSeries.length)
      : 0;

  // Flatten the daily-active series into the main table; everything
  // else (counts + top-5 lists) goes into the preface so the export
  // reads as a single "school report" file an admin can attach to an
  // email to the principal.
  //
  // Hook order: this useMemo lives BEFORE any conditional early return
  // so React's rules-of-hooks stays happy across data / loading / error
  // renders.
  const exportPreface = React.useMemo(() => {
    if (!data) return ["(no data)"];
    const top = (label: string, rows: SchoolTopUser[]) => [
      "",
      label,
      ...(rows.length === 0
        ? ["(none)"]
        : rows.map(
            (r, i) =>
              `${i + 1}. ${r.full_name}` +
              (r.class_section ? ` (${r.class_section})` : "") +
              ` — ${r.ai_sessions_7d} AI sessions in 7d`
          )),
    ];
    return [
      "Headcount",
      `Teachers: ${data.counts.teachers ?? 0}`,
      `Students: ${data.counts.students ?? 0}`,
      `Never logged in: ${data.counts.never_logged_in ?? 0}`,
      "",
      "Engagement",
      `Active this week: ${data.counts.active_7d ?? 0}`,
      `Active this month: ${data.counts.active_30d ?? 0}`,
      ...top("Most active teachers (7 days)", data.top_teachers_7d ?? []),
      ...top("Most active students (7 days)", data.top_students_7d ?? []),
    ];
  }, [data]);

  if (error) {
    return (
      <Card>
        <CardContent className="p-6">
          <EmptyState
            icon={<School className="h-5 w-5" />}
            title="Couldn't load the school overview"
            description={String((error as Error).message)}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <ExportButton
          label="Export school report"
          loading={isLoading}
          disabled={!data}
          options={() => ({
            subject: "School report",
            schoolName: user?.school_name ?? null,
            preface: exportPreface,
            columns: [
              { header: "Date", value: (r) => r.date },
              { header: "Daily active users", value: (r) => r.count },
            ] satisfies ExportColumn<{ date: string; count: number }>[],
            rows: data?.daily_active_14d ?? [],
          })}
        />
      </div>
      {/* ── Four headline tiles ─────────────────────────────────────── */}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatTile
          icon={<GraduationCap className="h-3.5 w-3.5" />}
          label="Teachers"
          value={counts?.teachers}
          loading={isLoading}
        />
        <StatTile
          icon={<BookOpen className="h-3.5 w-3.5" />}
          label="Students"
          value={counts?.students}
          loading={isLoading}
        />
        <StatTile
          icon={<UserCheck className="h-3.5 w-3.5" />}
          label="Active this week"
          value={counts?.active_7d}
          accent
          loading={isLoading}
        />
        <StatTile
          icon={<UserX className="h-3.5 w-3.5" />}
          label="Never logged in"
          value={counts?.never_logged_in}
          loading={isLoading}
        />
      </div>

      {/* ── 14-day daily-active sparkline ───────────────────────────── */}
      <Card>
        <CardContent className="p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Activity className="h-3.5 w-3.5" />
                Daily active users · last 14 days
              </div>
              {isLoading ? (
                <Skeleton className="mt-2 h-6 w-24" />
              ) : (
                <div className="mt-1 text-2xl font-bold tracking-tight tabular-nums">
                  {todayDau.toLocaleString()}
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    today · avg {avgDau}
                  </span>
                </div>
              )}
            </div>
            {isLoading ? (
              <Skeleton className="h-10 w-32" />
            ) : dauSeries.length >= 2 ? (
              <Sparkline
                data={dauSeries}
                width={160}
                height={40}
                className="text-primary"
              />
            ) : null}
          </div>
        </CardContent>
      </Card>

      {/* ── Top-5 strips, side by side on lg+ ───────────────────────── */}
      <div className="grid gap-3 lg:grid-cols-2">
        <TopStrip
          icon={<GraduationCap className="h-3.5 w-3.5" />}
          title="Most active teachers this week"
          users={data?.top_teachers_7d ?? []}
          loading={isLoading}
          emptyTitle="No teacher activity this week"
          emptyDescription="No teacher has used an AI feature in the last 7 days."
          hrefBase="/admin/teachers"
        />
        <TopStrip
          icon={<BookOpen className="h-3.5 w-3.5" />}
          title="Most active students this week"
          users={data?.top_students_7d ?? []}
          loading={isLoading}
          emptyTitle="No student activity this week"
          emptyDescription="No student has used an AI feature in the last 7 days."
          hrefBase="/admin/students"
          showClass
        />
      </div>
    </div>
  );
}

// ── Stat tile ─────────────────────────────────────────────────────────

function StatTile({
  icon,
  label,
  value,
  accent,
  loading,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | undefined;
  accent?: boolean;
  loading?: boolean;
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
        <div className="mt-1 text-2xl font-bold tracking-tight tabular-nums">
          {loading ? (
            <Skeleton className="h-7 w-16" />
          ) : (
            (value ?? 0).toLocaleString()
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Top-5 strip ───────────────────────────────────────────────────────

function TopStrip({
  icon,
  title,
  users,
  loading,
  emptyTitle,
  emptyDescription,
  hrefBase,
  showClass,
}: {
  icon: React.ReactNode;
  title: string;
  users: SchoolTopUser[];
  loading?: boolean;
  emptyTitle: string;
  emptyDescription: string;
  hrefBase: string;
  showClass?: boolean;
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {icon}
          {title}
        </div>
        {loading ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        ) : users.length === 0 ? (
          <EmptyState compact title={emptyTitle} description={emptyDescription} />
        ) : (
          <ol className="space-y-1">
            {users.map((u, i) => (
              <li key={u.id}>
                <Link
                  href={`${hrefBase}/${u.id}`}
                  className="flex items-center gap-3 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
                >
                  <span className="w-5 text-xs font-medium tabular-nums text-muted-foreground">
                    {i + 1}
                  </span>
                  <span className="flex-1 truncate">
                    {u.full_name}
                    {showClass && u.class_section && (
                      <span className="ml-1 text-xs text-muted-foreground">
                        · {u.class_section}
                      </span>
                    )}
                  </span>
                  <span className="text-xs font-medium tabular-nums text-muted-foreground">
                    {u.ai_sessions_7d.toLocaleString()}
                  </span>
                </Link>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
