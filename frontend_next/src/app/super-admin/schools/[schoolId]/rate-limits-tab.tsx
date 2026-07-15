"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  Infinity as InfinityIcon,
  Loader2,
  Lock,
  RotateCcw,
  Save,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { TokenBudgetPool } from "@/lib/types";

const ROLE_LABEL: Record<string, string> = {
  student: "Student",
  teacher: "Teacher",
};

const KINDS: { key: keyof TokenBudgetPool; label: string; icon: React.ReactNode }[] = [
  { key: "input", label: "Input tokens / day", icon: <ArrowUp className="h-3 w-3" /> },
  { key: "output", label: "Output tokens / day", icon: <ArrowDown className="h-3 w-3" /> },
];

function CapDecoration({ value }: { value: number }) {
  if (value === -1)
    return (
      <span className="inline-flex items-center gap-1 text-success">
        <InfinityIcon className="h-3 w-3" />
        <span className="text-[10px] font-medium uppercase tracking-wider">
          Unlimited
        </span>
      </span>
    );
  if (value === 0)
    return (
      <span className="inline-flex items-center gap-1 text-danger">
        <Lock className="h-3 w-3" />
        <span className="text-[10px] font-medium uppercase tracking-wider">
          Disabled
        </span>
      </span>
    );
  return null;
}

function countDirty(
  a: Record<string, TokenBudgetPool>,
  b: Record<string, TokenBudgetPool>
): number {
  let n = 0;
  for (const role of Object.keys(a)) {
    for (const k of ["input", "output"] as const) {
      if ((a[role]?.[k] ?? 0) !== (b[role]?.[k] ?? 0)) n += 1;
    }
  }
  return n;
}

export function SuperAdminSchoolRateLimitsTab({
  schoolId,
}: {
  schoolId: number;
}) {
  const qc = useQueryClient();
  const queryKey = ["super-admin-school-rate-limits", schoolId] as const;
  const { data, isLoading } = useQuery({
    queryKey,
    queryFn: () => api.superAdminGetSchoolLimits(schoolId),
  });

  const [draft, setDraft] = React.useState<Record<string, TokenBudgetPool> | null>(null);
  const [tracked, setTracked] = React.useState<Record<string, TokenBudgetPool> | null>(null);
  if (data?.limits && tracked !== data.limits) {
    setTracked(data.limits);
    setDraft(
      Object.fromEntries(
        Object.entries(data.limits).map(([r, p]) => [r, { ...p }])
      )
    );
  }

  const save = useMutation({
    mutationFn: () =>
      api.superAdminSetSchoolLimits(
        schoolId,
        draft as Record<string, TokenBudgetPool>
      ),
    onSuccess: () => {
      toast.success(`Override saved for school #${schoolId}.`);
      qc.invalidateQueries({ queryKey });
      qc.invalidateQueries({ queryKey: ["super-admin-schools"] });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  const clear = useMutation({
    mutationFn: () => api.superAdminClearSchoolLimits(schoolId),
    onSuccess: () => {
      toast.success("Override cleared. School will follow the default.");
      qc.invalidateQueries({ queryKey });
      qc.invalidateQueries({ queryKey: ["super-admin-schools"] });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  if (isLoading || !draft || !data) return <Skeleton className="h-64 w-full" />;

  const roles = (data.roles ?? Object.keys(draft)).filter(
    (r) => r !== "super_admin" && r !== "admin"
  );
  const dirty = JSON.stringify(draft) !== JSON.stringify(data.limits);
  const dirtyCount = countDirty(draft, data.limits);
  const overrides = data.overrides ?? {};

  return (
    <div className="space-y-4 pb-20">
      <Card>
        <CardContent className="p-4 text-xs text-muted-foreground">
          {data.has_override ? (
            <>
              This school has a <strong>custom override</strong>. Clearing it
              makes the school fall back to the platform default for both
              input and output pools.
            </>
          ) : (
            <>
              This school uses the <strong>platform default</strong>. Editing
              any value here creates a school-specific override.
            </>
          )}
        </CardContent>
      </Card>

      {roles.map((role) => {
        const pool = draft[role] ?? { input: 0, output: 0 };
        const orig = data.limits[role] ?? pool;
        const overridden = overrides[role] !== undefined;
        return (
          <Card key={role}>
            <CardContent className="space-y-4 p-5">
              <h3 className="text-sm font-semibold">
                {ROLE_LABEL[role] ?? role}{" "}
                <span className="ml-1 text-xs font-normal text-muted-foreground">
                  {overridden ? "(school override)" : "(inherited)"}
                </span>
              </h3>
              <div className="grid gap-4 sm:grid-cols-2">
                {KINDS.map(({ key, label, icon }) => {
                  const value = pool[key] ?? 0;
                  const original = orig[key] ?? value;
                  const isDirty = value !== original;
                  return (
                    <div key={key} className="space-y-1.5">
                      <div className="flex items-baseline justify-between gap-2">
                        <label
                          htmlFor={`rl-${role}-${key}`}
                          className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground"
                        >
                          {icon}
                          {label}
                        </label>
                        <CapDecoration value={value} />
                      </div>
                      <Input
                        id={`rl-${role}-${key}`}
                        type="number"
                        min={-1}
                        value={value}
                        onChange={(e) =>
                          setDraft((prev) => ({
                            ...(prev || {}),
                            [role]: {
                              ...(prev?.[role] || { input: 0, output: 0 }),
                              [key]: Number(e.target.value),
                            },
                          }))
                        }
                        className={cn(
                          "h-10 tabular-nums",
                          isDirty && "border-warning ring-1 ring-warning/30"
                        )}
                      />
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        );
      })}

      {data.has_override && (
        <Button
          variant="outline"
          size="sm"
          onClick={() => clear.mutate()}
          disabled={clear.isPending}
        >
          {clear.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Trash2 className="h-3.5 w-3.5" />
          )}
          Clear override (use default)
        </Button>
      )}

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
                  setDraft(
                    Object.fromEntries(
                      Object.entries(data.limits).map(([r, p]) => [r, { ...p }])
                    )
                  )
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
                Save
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
