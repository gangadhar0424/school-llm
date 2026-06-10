"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/client-api";
import { Progress } from "@/components/ui/progress";
import { formatResetCountdown } from "@/lib/utils";
import type { MyRateLimits } from "@/lib/types";

const FEATURE_DISPLAY: Record<string, { icon: string; label: string; order: number }> = {
  qa: { icon: "💬", label: "Q&A", order: 1 },
  summary: { icon: "📋", label: "Summary", order: 2 },
  quiz: { icon: "📝", label: "Quiz", order: 3 },
  audio: { icon: "🔊", label: "Audio", order: 4 },
  video: { icon: "🎬", label: "Video", order: 5 },
  short_answer: { icon: "📝", label: "Short Answers", order: 1 },
  long_answer: { icon: "📄", label: "Long Answers", order: 2 },
  mcq: { icon: "🎲", label: "Quizzes (MCQ)", order: 3 },
  fill_in_blank: { icon: "✏️", label: "Fill in the Blanks", order: 4 },
  question_paper: { icon: "📜", label: "Question Paper", order: 5 },
};

const WARN_AT = 0.8;

export const USAGE_QUERY_KEY = ["my-rate-limits"] as const;

function bandColor(ratio: number): string {
  if (ratio >= 0.95) return "🔴";
  if (ratio >= WARN_AT) return "🟡";
  return "🟢";
}

export function UsageRibbon() {
  const { data } = useQuery<MyRateLimits>({
    queryKey: USAGE_QUERY_KEY,
    queryFn: api.myRateLimits,
    // Refresh every minute so the reset countdown drifts forward, but
    // the bulk of updates come from mutation invalidations.
    refetchInterval: 60_000,
  });

  if (!data) return null;
  const entries = Object.entries(data.features)
    .map(([key, info]) => ({ key, info, meta: FEATURE_DISPLAY[key] }))
    .filter((e) => e.meta && (e.info.limit !== 0))
    .sort((a, b) => (a.meta?.order ?? 99) - (b.meta?.order ?? 99));

  if (entries.length === 0) return null;

  return (
    <div className="rounded-lg border border-sidebar-border p-3 text-sidebar-foreground">
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-sidebar-muted">
        📊 Today&apos;s AI usage
      </div>
      <div className="space-y-2">
        {entries.map(({ key, info, meta }) => {
          const limit = info.limit;
          const used = info.used;
          if (limit < 0) {
            return (
              <div
                key={key}
                className="flex items-center justify-between text-xs"
              >
                <span>
                  {meta?.icon} {meta?.label}
                </span>
                <span className="text-sidebar-muted">
                  <strong className="text-sidebar-foreground">
                    {used}
                  </strong>{" "}
                  unlimited
                </span>
              </div>
            );
          }
          const ratio = Math.max(0, Math.min(1, limit > 0 ? used / limit : 0));
          return (
            <div key={key} className="text-xs">
              <div className="flex items-center justify-between">
                <span>
                  {meta?.icon} {meta?.label} {bandColor(ratio)}
                </span>
                <span className="text-sidebar-muted">
                  <strong className="text-sidebar-foreground">
                    {used}
                  </strong>{" "}
                  / {limit}
                </span>
              </div>
              <Progress
                value={ratio * 100}
                className="mt-1 h-1.5 bg-sidebar-border"
              />
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-[10px] text-sidebar-muted">
        ⏱ Resets in {formatResetCountdown(data.resets_in_seconds)}
      </p>
    </div>
  );
}
