"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  Infinity as InfinityIcon,
  Loader2,
  Lock,
  RotateCcw,
  Save,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const LIMITS_KEY = ["admin-rate-limits"] as const;

// Friendly display names. Anything missing falls back to the raw key.
const FEATURE_LABELS: Record<string, string> = {
  qa: "Q&A",
  summary: "Summaries",
  quiz: "Quiz",
  audio: "Audio narration",
  video: "Video generation",
  short_answer: "Short answer (gen)",
  long_answer: "Long answer (gen)",
  mcq: "MCQ (gen)",
  fill_in_blank: "Fill-in-the-blank (gen)",
  question_paper: "Question paper",
};

const ROLE_BLURB: Record<string, string> = {
  admin:
    "Admin accounts run reports and demos — usually unlimited or very high.",
  teacher:
    "Teachers generate questions for assignments; limits should comfortably cover a full class set per day.",
  student:
    "Students consume AI tools to study — set limits per the school's daily-fair-use policy.",
};

/**
 * Format a limit cap as either a number, "Unlimited", or "Disabled". The
 * `-1` and `0` sentinels are how the backend signals "no cap" and
 * "fully disabled"; the input value still stays numeric so admins can
 * type into it directly, but the visual decoration here makes the
 * meaning obvious without staring at a -1 or 0.
 */
function CapDecoration({ value }: { value: number }) {
  if (value === -1) {
    return (
      <span className="inline-flex items-center gap-1 text-success">
        <InfinityIcon className="h-3 w-3" />
        <span className="text-[10px] font-medium uppercase tracking-wider">
          Unlimited
        </span>
      </span>
    );
  }
  if (value === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-danger">
        <Lock className="h-3 w-3" />
        <span className="text-[10px] font-medium uppercase tracking-wider">
          Disabled
        </span>
      </span>
    );
  }
  return null;
}

export function AdminRateLimitsClient() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: LIMITS_KEY,
    queryFn: api.adminGetRateLimits,
  });

  // Tracked-prop pattern (React 19 forbids setState in effects). When
  // the server-fetched `data.limits` reference changes (initial load,
  // after Save invalidates), snapshot it into the draft so the admin
  // can edit. Local edits stay until Reset or Save.
  const [draft, setDraft] = React.useState<
    Record<string, Record<string, number>> | null
  >(null);
  const [trackedLimits, setTrackedLimits] = React.useState<
    Record<string, Record<string, number>> | null
  >(null);
  if (data?.limits && trackedLimits !== data.limits) {
    setTrackedLimits(data.limits);
    setDraft(JSON.parse(JSON.stringify(data.limits)));
  }

  // Open/closed state per role section.
  const [collapsed, setCollapsed] = React.useState<Record<string, boolean>>({});

  const save = useMutation({
    mutationFn: () =>
      api.adminUpdateRateLimits(draft as Record<string, Record<string, number>>),
    onSuccess: () => {
      toast.success("Limits updated.");
      qc.invalidateQueries({ queryKey: LIMITS_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  if (isLoading || !draft) return <Skeleton className="h-64 w-full" />;
  if (!data) return null;

  const roles = Object.keys(draft);
  const usage = data.usage_today ?? {};

  // Are there unsaved changes? Drives the floating save bar.
  const dirty = JSON.stringify(draft) !== JSON.stringify(data.limits);
  const dirtyCount = countDirty(draft, data.limits);

  return (
    <div className="space-y-4 pb-20">
      {roles.map((role) => {
        const features = Object.keys(draft[role] || {}).sort();
        const isCollapsed = collapsed[role];
        const roleUsage = usage[role] || {};
        const roleDirty = countDirty(
          { [role]: draft[role] },
          { [role]: data.limits[role] || {} }
        );
        return (
          <Card key={role}>
            <CardContent className="p-0">
              <button
                onClick={() =>
                  setCollapsed((c) => ({ ...c, [role]: !c[role] }))
                }
                className="flex w-full items-center gap-2 border-b border-border px-5 py-3 text-left transition-colors hover:bg-muted/40"
                aria-expanded={!isCollapsed}
              >
                {isCollapsed ? (
                  <ChevronRight className="h-4 w-4 text-muted-foreground" />
                ) : (
                  <ChevronDown className="h-4 w-4 text-muted-foreground" />
                )}
                <span className="text-sm font-semibold capitalize">{role}</span>
                <Badge variant="outline" className="text-[10px]">
                  {features.length} features
                </Badge>
                {roleDirty > 0 && (
                  <Badge variant="warning" className="text-[10px]">
                    {roleDirty} unsaved
                  </Badge>
                )}
                <span className="ml-auto text-xs text-muted-foreground">
                  {ROLE_BLURB[role] || "Per-user daily caps."}
                </span>
              </button>

              {!isCollapsed && (
                <div className="grid gap-x-4 gap-y-3 p-5 sm:grid-cols-2 lg:grid-cols-3">
                  {features.map((feat) => {
                    const value = draft[role][feat];
                    const original = data.limits[role]?.[feat] ?? value;
                    const usedToday = roleUsage[feat] ?? 0;
                    const isDirty = value !== original;
                    return (
                      <div key={feat} className="space-y-1.5">
                        <div className="flex items-baseline justify-between gap-2">
                          <label
                            htmlFor={`rl-${role}-${feat}`}
                            className="text-xs font-medium"
                          >
                            {FEATURE_LABELS[feat] || feat}
                          </label>
                          <CapDecoration value={value} />
                        </div>
                        <Input
                          id={`rl-${role}-${feat}`}
                          type="number"
                          min={-1}
                          value={value}
                          onChange={(e) =>
                            setDraft((prev) => ({
                              ...(prev || {}),
                              [role]: {
                                ...(prev?.[role] || {}),
                                [feat]: Number(e.target.value),
                              },
                            }))
                          }
                          className={cn(
                            "h-9 tabular-nums",
                            isDirty && "border-warning ring-1 ring-warning/30"
                          )}
                        />
                        <p className="text-[10px] text-muted-foreground">
                          <span className="font-medium text-foreground tabular-nums">
                            {usedToday.toLocaleString()}
                          </span>{" "}
                          used today{" "}
                          {value > 0 && (
                            <span className="text-muted-foreground/60">
                              · {Math.round((usedToday / value) * 100)}% of cap
                            </span>
                          )}
                        </p>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        );
      })}

      {/* Floating save bar — appears only when there are unsaved changes */}
      {dirty && (
        <div className="fixed bottom-4 left-1/2 z-30 w-full max-w-2xl -translate-x-1/2 rounded-lg border border-border bg-surface px-4 py-2.5 shadow-lg">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-xs">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-warning" />
              <span>
                <strong className="text-foreground">{dirtyCount}</strong>{" "}
                unsaved {dirtyCount === 1 ? "change" : "changes"}
              </span>
            </div>
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  setDraft(JSON.parse(JSON.stringify(data.limits)))
                }
                disabled={save.isPending}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Discard
              </Button>
              <Button
                size="sm"
                onClick={() => save.mutate()}
                disabled={save.isPending}
              >
                {save.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="h-3.5 w-3.5" />
                )}
                Save changes
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function countDirty(
  draft: Record<string, Record<string, number>> | null,
  base: Record<string, Record<string, number>> | null
): number {
  if (!draft || !base) return 0;
  let n = 0;
  for (const role of Object.keys(draft)) {
    for (const feat of Object.keys(draft[role] || {})) {
      if (draft[role][feat] !== (base[role]?.[feat] ?? draft[role][feat])) {
        n += 1;
      }
    }
  }
  return n;
}
