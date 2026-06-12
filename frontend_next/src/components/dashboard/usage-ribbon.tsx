"use client";

import { Info } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/client-api";
import { Progress } from "@/components/ui/progress";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
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
    // Refresh every minute (visible tabs only) so the reset countdown
    // drifts forward; mutations that consume quota invalidate this key
    // directly for instant updates.
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

  if (!data) return null;
  const entries = Object.entries(data.features)
    .map(([key, info]) => ({ key, info, meta: FEATURE_DISPLAY[key] }))
    .filter((e) => e.meta && (e.info.limit !== 0))
    .sort((a, b) => (a.meta?.order ?? 99) - (b.meta?.order ?? 99));

  if (entries.length === 0) return null;

  return (
    <div className="rounded-lg border border-sidebar-border p-3 text-sidebar-foreground">
      <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-sidebar-muted">
        <span>📊 Today&apos;s AI usage</span>
        <UsageInfoPopover />
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

/**
 * Small "i" info icon next to the "Today's AI usage" label. Clicking it
 * opens a popover that explains where the daily caps come from. Shared
 * across roles (admin / teacher / student) since UsageRibbon is shared.
 *
 * Copy intentionally focuses on *how the limits are set* (admin policy)
 * rather than what counts as a "use" — that's the question this label
 * gets in school staff rooms the most.
 */
function UsageInfoPopover() {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="How AI usage limits are set"
          className="inline-flex h-4 w-4 items-center justify-center rounded-full text-sidebar-muted hover:text-sidebar-foreground"
        >
          <Info className="h-3.5 w-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        side="right"
        align="start"
        className="w-72 text-xs"
      >
        <p className="font-medium">How AI usage limits are set</p>
        <p className="mt-1.5 text-muted-foreground">
          Your school administrator sets a daily cap for each AI feature.
          Caps are configured <strong>per role</strong> (teacher, student,
          admin) — every teacher at your school shares the same daily
          quota for Q&amp;A, every student shares their own, and so on.
        </p>
        <p className="mt-2 text-muted-foreground">
          The number on the left of each bar is what you&apos;ve used so
          far today; the number on the right is your role&apos;s daily
          cap. A cap of <code>-1</code> means unlimited; <code>0</code>{" "}
          means the feature is turned off for your role.
        </p>
        <p className="mt-2 text-muted-foreground">
          Counters reset at midnight in the school&apos;s timezone. If a
          feature feels too tight, ask your admin to raise the cap in
          <em> Permissions &amp; Rate limits</em>.
        </p>
      </PopoverContent>
    </Popover>
  );
}
