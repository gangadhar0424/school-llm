"use client";

import { ArrowDown, ArrowUp, Info } from "lucide-react";
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
import type { MyRateLimits, RateLimitInfo } from "@/lib/types";

const FEATURE_LABEL: Record<string, string> = {
  qa: "Q&A",
  summary: "Summary",
  quiz: "Quiz",
  audio: "Audio",
  video: "Video",
  short_answer: "Short answer",
  long_answer: "Long answer",
  mcq: "MCQ",
  fill_in_blank: "Fill in the blank",
  question_paper: "Question paper",
};
const WARN_AT = 0.8;

export const USAGE_QUERY_KEY = ["my-rate-limits"] as const;

export function UsageCard() {
  const { data, isPending } = useQuery<MyRateLimits>({
    queryKey: USAGE_QUERY_KEY,
    queryFn: api.myRateLimits,
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

  // Either pool being disabled means the role is effectively disabled.
  if (data.input.limit === 0 || data.output.limit === 0) {
    return (
      <Card>
        <CardContent className="p-5 text-sm text-muted-foreground">
          AI features are currently disabled for your role. Please contact
          your administrator.
        </CardContent>
      </Card>
    );
  }

  const breakdown = Object.entries(data.by_feature || {})
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);

  return (
    <Card>
      <CardContent className="p-5">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-semibold text-foreground">
            📊 Today&apos;s AI token usage
          </h3>
          <Popover>
            <PopoverTrigger asChild>
              <button
                type="button"
                aria-label="How AI usage is measured"
                className="inline-flex h-5 w-5 items-center justify-center rounded-full text-muted-foreground hover:text-foreground"
              >
                <Info className="h-3.5 w-3.5" />
              </button>
            </PopoverTrigger>
            <PopoverContent side="bottom" align="start" className="w-80 text-xs">
              <p className="font-medium">How AI usage is measured</p>
              <p className="mt-1.5 text-muted-foreground">
                Your usage is split into <strong>input</strong> tokens (your
                prompt + PDF context) and <strong>output</strong> tokens (what
                the AI writes back) — just like Claude or ChatGPT plans bill.
                Every AI call deducts from both pools.
              </p>
              <p className="mt-2 text-muted-foreground">
                When either pool runs out, AI features pause until midnight.
                Ask your administrator for a higher cap if you need more.
              </p>
            </PopoverContent>
          </Popover>
        </div>

        <p className="text-xs text-muted-foreground">
          Resets in{" "}
          <strong>{formatResetCountdown(data.resets_in_seconds)}</strong>.
        </p>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <BudgetTile
            icon={<ArrowUp className="h-3.5 w-3.5" />}
            label="Input"
            info={data.input}
            hint="Prompt + PDF context"
          />
          <BudgetTile
            icon={<ArrowDown className="h-3.5 w-3.5" />}
            label="Output"
            info={data.output}
            hint="AI-generated response"
          />
        </div>

        {breakdown.length > 0 && (
          <div className="mt-4">
            <p className="text-xs uppercase tracking-wider text-muted-foreground">
              Used today by feature (input + output)
            </p>
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
              {breakdown.map(([key, tokens]) => (
                <div
                  key={key}
                  className="rounded border border-border bg-surface px-2 py-1.5 text-xs"
                >
                  <div className="text-muted-foreground">
                    {FEATURE_LABEL[key] ?? key}
                  </div>
                  <div className="tabular-nums">{tokens.toLocaleString()}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function BudgetTile({
  icon,
  label,
  info,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  info: RateLimitInfo;
  hint: string;
}) {
  const { limit, used, remaining } = info;
  const isUnlimited = limit < 0;
  const ratio = isUnlimited
    ? 0
    : Math.max(0, Math.min(1, used / Math.max(limit, 1)));
  const tone =
    !isUnlimited && remaining === 0
      ? "text-danger"
      : !isUnlimited && ratio >= WARN_AT
        ? "text-warning"
        : "text-success";

  return (
    <div className="rounded-lg border border-border bg-surface-2 p-4">
      <div className="flex items-baseline justify-between gap-2">
        <span className="inline-flex items-center gap-1 text-xs uppercase tracking-wider text-muted-foreground">
          {icon}
          {label}
        </span>
        <span className={`text-xs font-medium ${tone}`}>
          {isUnlimited
            ? "Unlimited"
            : remaining === 0
              ? "Limit reached"
              : `${remaining?.toLocaleString()} left`}
        </span>
      </div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="text-2xl font-semibold tabular-nums">
          {used.toLocaleString()}
        </span>
        {!isUnlimited && (
          <span className="text-sm text-muted-foreground tabular-nums">
            / {limit.toLocaleString()}
          </span>
        )}
        <span className="text-xs text-muted-foreground">tokens</span>
      </div>
      {!isUnlimited && <Progress value={ratio * 100} className="mt-3 h-1.5" />}
      <p className="mt-2 text-[10px] text-muted-foreground">{hint}</p>
    </div>
  );
}
