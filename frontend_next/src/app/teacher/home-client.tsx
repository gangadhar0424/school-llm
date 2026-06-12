"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Activity, ClipboardCheck, Cpu, FileText } from "lucide-react";
import { api } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { LineChart } from "@/components/ui/sparkline";
import { UsageCard } from "@/components/dashboard/usage-card";
import {
  AnalyticsPeriodTabs,
  FeatureBars,
  KpiCard,
} from "@/components/dashboard/analytics-primitives";
import type { TeacherAnalyticsPeriod } from "@/lib/types";

export const TEACHER_ASSIGNMENTS_KEY = ["teacher-assignments"] as const;
export const TEACHER_STUDENTS_KEY = ["teacher-students"] as const;
export const TEACHER_ANALYTICS_KEY = (p: TeacherAnalyticsPeriod) =>
  ["teacher-analytics", p] as const;

const PERIODS: { value: TeacherAnalyticsPeriod; label: string }[] = [
  { value: "1d", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
  { value: "90d", label: "90d" },
];

// Teacher-side AI features only. Q&A / Summary / Quiz / Audio / Video
// are student-side flows that a teacher account never fires, so they're
// intentionally absent — keeps the Feature usage card honest.
const FEATURE_LABEL: Record<string, string> = {
  short_answer: "Short answer",
  long_answer: "Long answer",
  mcq: "MCQ",
  fill_in_blank: "Fill in blank",
  true_false: "True / False",
  question_paper: "Question paper",
};

export function TeacherHomeClient() {
  const [period, setPeriod] = React.useState<TeacherAnalyticsPeriod>("30d");

  const { data: assignments, isLoading: aLoading } = useQuery({
    queryKey: TEACHER_ASSIGNMENTS_KEY,
    queryFn: api.teacherListAssignments,
  });
  const { data: analytics, isLoading: anLoading } = useQuery({
    queryKey: TEACHER_ANALYTICS_KEY(period),
    queryFn: () => api.teacherAnalytics(period),
  });

  const list = assignments?.assignments ?? [];
  const counts = analytics?.counts;
  const featureUsage = analytics?.feature_usage ?? {};
  const daily = analytics?.daily_activity ?? [];
  const perClass = analytics?.per_class ?? [];

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      {/* Quota ribbon stays at the top — it's the most-asked-about UI */}
      <UsageCard />

      {/* ── Analytics block (mirrors /admin layout) ──────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Your AI usage</h2>
          <p className="text-xs text-muted-foreground">
            How you&apos;ve been using the LLM in the selected period.
          </p>
        </div>
        <AnalyticsPeriodTabs
          value={period}
          onChange={setPeriod}
          periods={PERIODS}
        />
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard
          icon={<FileText className="h-4 w-4" />}
          label="PDFs uploaded"
          value={counts?.pdfs_uploaded}
          loading={anLoading}
        />
        <KpiCard
          icon={<ClipboardCheck className="h-4 w-4" />}
          label="Assignments created"
          value={counts?.assignments_created}
          loading={anLoading}
        />
        <KpiCard
          icon={<Activity className="h-4 w-4 text-success" />}
          label="Submissions graded"
          value={counts?.submissions_graded}
          accent
          loading={anLoading}
        />
        <KpiCard
          icon={<Cpu className="h-4 w-4" />}
          label={`AI sessions (${period})`}
          value={counts?.ai_sessions_period}
          loading={anLoading}
          sparkline={daily.map((d) => d.count)}
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
          {anLoading ? (
            <Skeleton className="mt-3 h-48 w-full" />
          ) : (
            <LineChart data={daily} className="mt-3" />
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
                Your AI feature invocations in the selected period.
              </p>
            </div>
            {!anLoading && (
              <span className="text-xs text-muted-foreground">
                {Object.values(featureUsage).reduce((a, b) => a + b, 0)} total
              </span>
            )}
          </div>
          {anLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : (
            <FeatureBars usage={featureUsage} labels={FEATURE_LABEL} />
          )}
        </CardContent>
      </Card>

      {/* Per-class breakdown */}
      {perClass.length > 0 && (
        <Card>
          <CardContent className="p-5">
            <h3 className="mb-3 text-sm font-semibold">Per-class activity</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-2 py-2 text-left">Class</th>
                    <th className="px-2 py-2 text-right">Students</th>
                    <th className="px-2 py-2 text-right">Assignments</th>
                    <th className="px-2 py-2 text-right">Submissions</th>
                  </tr>
                </thead>
                <tbody>
                  {perClass.map((row) => (
                    <tr
                      key={row.class_section}
                      className="border-b border-border last:border-0"
                    >
                      <td className="px-2 py-2">
                        <Badge variant="secondary">{row.class_section}</Badge>
                      </td>
                      <td className="px-2 py-2 text-right tabular-nums">
                        {row.students}
                      </td>
                      <td className="px-2 py-2 text-right tabular-nums">
                        {row.assignments}
                      </td>
                      <td className="px-2 py-2 text-right tabular-nums">
                        {row.submissions}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── Recent assignments ─────────────────────────────────────── */}
      <section>
        <h2 className="mb-3 text-base font-semibold">Recent assignments</h2>
        {aLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : list.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              You haven&apos;t created any assignments yet.
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-2">
            {list.slice(0, 5).map((a) => (
              <Card key={a.id}>
                <CardContent className="flex items-center justify-between gap-3 p-4">
                  <div className="min-w-0">
                    <Link
                      href={`/teacher/assignments/${a.id}`}
                      className="truncate text-sm font-medium hover:underline"
                    >
                      {a.title}
                    </Link>
                    <p className="text-xs text-muted-foreground">
                      Class {a.class_section}
                      {a.subject ? ` · ${a.subject}` : ""} · {a.questions.length} Q
                      · {a.submission_count ?? 0} submissions
                    </p>
                  </div>
                  <Badge
                    variant={
                      a.status === "published"
                        ? "success"
                        : a.status === "draft"
                          ? "warning"
                          : "outline"
                    }
                  >
                    {a.status}
                  </Badge>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
