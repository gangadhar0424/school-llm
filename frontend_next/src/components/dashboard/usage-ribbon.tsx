"use client";

import { ArrowDown, ArrowUp, Info } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/client-api";
import { Progress } from "@/components/ui/progress";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { formatResetCountdown } from "@/lib/utils";
import type { MyRateLimits, RateLimitInfo } from "@/lib/types";

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
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });

  if (!data) return null;

  // Either pool disabled — hide entirely.
  if (data.input.limit === 0 || data.output.limit === 0) return null;

  return (
    <div className="rounded-lg border border-sidebar-border p-3 text-sidebar-foreground">
      <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-sidebar-muted">
        <span>📊 Today&apos;s AI tokens</span>
        <UsageInfoPopover />
      </div>

      <div className="space-y-2">
        <BudgetRow
          icon={<ArrowUp className="h-3 w-3" />}
          label="Input"
          info={data.input}
        />
        <BudgetRow
          icon={<ArrowDown className="h-3 w-3" />}
          label="Output"
          info={data.output}
        />
      </div>

      <p className="mt-2 text-[10px] text-sidebar-muted">
        ⏱ Resets in {formatResetCountdown(data.resets_in_seconds)}
      </p>
    </div>
  );
}

function BudgetRow({
  icon,
  label,
  info,
}: {
  icon: React.ReactNode;
  label: string;
  info: RateLimitInfo;
}) {
  const { limit, used } = info;
  const isUnlimited = limit < 0;
  const ratio = isUnlimited
    ? 0
    : Math.max(0, Math.min(1, used / Math.max(limit, 1)));

  return (
    <div className="text-xs">
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-1">
          {icon}
          {label} {!isUnlimited && bandColor(ratio)}
        </span>
        <span className="text-sidebar-muted tabular-nums">
          <strong className="text-sidebar-foreground">
            {used.toLocaleString()}
          </strong>
          {isUnlimited ? (
            <span className="ml-1">· ∞</span>
          ) : (
            <> / {limit.toLocaleString()}</>
          )}
        </span>
      </div>
      {!isUnlimited && (
        <Progress
          value={ratio * 100}
          className="mt-1 h-1 bg-sidebar-border"
        />
      )}
    </div>
  );
}

function UsageInfoPopover() {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label="How AI usage is measured"
          className="inline-flex h-4 w-4 items-center justify-center rounded-full text-sidebar-muted hover:text-sidebar-foreground"
        >
          <Info className="h-3.5 w-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent side="right" align="start" className="w-72 text-xs">
        <p className="font-medium">How AI usage is measured</p>
        <p className="mt-1.5 text-muted-foreground">
          Your usage is split into <strong>input</strong> tokens (your prompt +
          PDF context) and <strong>output</strong> tokens (what the AI writes
          back). When either pool empties, AI features pause until midnight.
        </p>
      </PopoverContent>
    </Popover>
  );
}
