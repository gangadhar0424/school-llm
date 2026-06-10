"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

const LIMITS_KEY = ["admin-rate-limits"] as const;

export function AdminRateLimitsClient() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: LIMITS_KEY,
    queryFn: api.adminGetRateLimits,
  });
  // Server-fetched limits feed into a local "draft" the admin edits.
  // React 19 forbids setState in effects, so we use the tracked-prop
  // pattern: when the fetched `data.limits` reference changes, snapshot
  // it into the draft during render. The admin's edits stay in the draft
  // until they explicitly Reset or Save.
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

  return (
    <div className="space-y-4">
      {roles.map((role) => {
        const features = Object.keys(draft[role] || {}).sort();
        return (
          <Card key={role}>
            <CardContent className="p-5">
              <h3 className="mb-3 text-sm font-semibold capitalize">
                {role} — per day
              </h3>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {features.map((feat) => (
                  <div key={feat}>
                    <label className="text-xs text-muted-foreground">
                      {feat}
                    </label>
                    <Input
                      type="number"
                      min={-1}
                      value={draft[role][feat]}
                      onChange={(e) =>
                        setDraft((prev) => ({
                          ...(prev || {}),
                          [role]: {
                            ...(prev?.[role] || {}),
                            [feat]: Number(e.target.value),
                          },
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        );
      })}
      <div className="flex justify-end gap-2">
        <Button
          variant="outline"
          onClick={() => setDraft(JSON.parse(JSON.stringify(data.limits)))}
        >
          <RotateCcw className="h-4 w-4" /> Reset
        </Button>
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          {save.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Save limits
        </Button>
      </div>
    </div>
  );
}
