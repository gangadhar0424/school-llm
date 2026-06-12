"use client";

import { Info } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { formatResetCountdown } from "@/lib/utils";
import type { MyRateLimits } from "@/lib/types";

const FEATURE_DISPLAY: Record<
  string,
  { icon: string; label: string; order: number }
> = {
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

export function UsageCard() {
  const { data, isPending } = useQuery<MyRateLimits>({
    queryKey: USAGE_QUERY_KEY,
    queryFn: api.myRateLimits,
    // Once per minute, only while the tab is visible. Mutations that
    // consume quota (quiz, summary, audio, video, ask) invalidate this
    // key directly, so users see their usage tick up immediately
    // without waiting for the next poll.
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

  if (isPending) {
    return (
      <Card>
        <CardContent className="p-5 text-sm text-muted-foreground">
          Loading usage…
        </CardContent>
      </Card>
    );
  }
  if (!data) {
    return (
      <Card>
        <CardContent className="p-5 text-sm text-muted-foreground">
          Usage data unavailable right now.
        </CardContent>
      </Card>
    );
  }

  const entries = Object.entries(data.features)
    .map(([key, info]) => ({ key, info, meta: FEATURE_DISPLAY[key] }))
    .filter((e) => e.meta && e.info.limit !== 0)
    .sort((a, b) => (a.meta?.order ?? 99) - (b.meta?.order ?? 99));

  if (entries.length === 0) {
    return (
      <Card>
        <CardContent className="p-5 text-sm text-muted-foreground">
          No AI features are enabled for your account.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-semibold text-foreground">
            📊 Today&apos;s AI usage
          </h3>
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                aria-label="How AI usage limits are set"
                className="inline-flex h-5 w-5 items-center justify-center rounded-full text-muted-foreground hover:text-foreground"
              >
                <Info className="h-3.5 w-3.5" />
              </button>
            </PopoverTrigger>
            <PopoverContent side="bottom" align="start" className="w-80 text-xs">
              <p className="font-medium">How AI usage limits are set</p>
              <p className="mt-1.5 text-muted-foreground">
                Your school administrator sets a daily cap for each AI
                feature. Caps are configured <strong>per role</strong>{" "}
                (teacher, student, admin) — every teacher at your school
                shares the same daily quota for Q&amp;A, every student
                shares their own, and so on.
              </p>
              <p className="mt-2 text-muted-foreground">
                The number on the left of each tile is what you&apos;ve
                used today; the number on the right is your role&apos;s
                daily cap. A cap of <code>-1</code> means unlimited;{" "}
                <code>0</code> means the feature is turned off for your
                role.
              </p>
              <p className="mt-2 text-muted-foreground">
                Counters reset at midnight in the school&apos;s timezone.
                If a feature feels too tight, ask your admin to raise
                the cap in <em>Permissions &amp; Rate limits</em>.
              </p>
            </PopoverContent>
          </Popover>
        </div>
        <p className="text-xs text-muted-foreground">
          Quotas reset in{" "}
          <strong>{formatResetCountdown(data.resets_in_seconds)}</strong>. Need
          more? Ask your administrator to raise your limit.
        </p>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {entries.map(({ key, info, meta }) => {
            const limit = info.limit;
            const used = info.used;
            if (limit < 0) {
              return (
                <div
                  key={key}
                  className="rounded-lg border border-border bg-surface-2 p-3"
                >
                  <div className="text-xs text-muted-foreground">
                    {meta?.icon} {meta?.label}
                  </div>
                  <div className="mt-1 text-xl font-semibold">{used}</div>
                  <div className="text-[10px] text-muted-foreground">
                    Unlimited
                  </div>
                </div>
              );
            }
            const remaining = Math.max(0, limit - used);
            const ratio = Math.max(0, Math.min(1, used / limit));
            const tone =
              remaining === 0
                ? "text-danger"
                : ratio >= WARN_AT
                  ? "text-warning"
                  : "text-success";
            return (
              <div
                key={key}
                className="rounded-lg border border-border bg-surface-2 p-3"
              >
                <div className="text-xs text-muted-foreground">
                  {meta?.icon} {meta?.label}
                </div>
                <div className="mt-1 text-xl font-semibold">
                  {used}{" "}
                  <span className="text-sm text-muted-foreground">/ {limit}</span>
                </div>
                <div className={`text-[10px] ${tone}`}>
                  {remaining > 0 ? `${remaining} left` : "Limit reached"}
                </div>
                <Progress value={ratio * 100} className="mt-2 h-1.5" />
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
