"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, FlaskConical } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelative } from "@/lib/utils";
import type { EvalItem, EvalRun } from "@/lib/types";

const RUNS_KEY = ["admin-eval-runs"] as const;

export function AdminEvalClient() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: RUNS_KEY,
    queryFn: () => api.adminEvalListRuns(30),
  });

  const [activeRun, setActiveRun] = React.useState<string | null>(null);

  const triggerSuccess = () => {
    toast.success("Run started. Refresh in a moment.");
    qc.invalidateQueries({ queryKey: RUNS_KEY });
  };

  const onQA = useMutation({
    mutationFn: (limit: number) => api.adminEvalRunOnQA({ limit }),
    onSuccess: triggerSuccess,
    onError: (e: ApiError) => toast.error(e.message),
  });
  const onSums = useMutation({
    mutationFn: (limit: number) => api.adminEvalRunOnSummaries({ limit }),
    onSuccess: triggerSuccess,
    onError: (e: ApiError) => toast.error(e.message),
  });
  const onQuizzes = useMutation({
    mutationFn: (limit: number) => api.adminEvalRunOnQuizzes({ limit }),
    onSuccess: triggerSuccess,
    onError: (e: ApiError) => toast.error(e.message),
  });
  const onBundle = useMutation({
    mutationFn: (limit: number) => api.adminEvalRunStudentBundle({ limit }),
    onSuccess: triggerSuccess,
    onError: (e: ApiError) => toast.error(e.message),
  });

  const [limit, setLimit] = React.useState(20);

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-3 p-5">
          <h3 className="text-sm font-semibold">Trigger an eval run</h3>
          <div className="flex items-end gap-3">
            <div>
              <Label>Sample size</Label>
              <Input
                type="number"
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value) || 20)}
                className="w-24"
              />
            </div>
            <Button
              size="sm"
              onClick={() => onQA.mutate(limit)}
              disabled={onQA.isPending}
            >
              {onQA.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              Run on Q&A
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => onSums.mutate(limit)}
              disabled={onSums.isPending}
            >
              Summaries
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => onQuizzes.mutate(limit)}
              disabled={onQuizzes.isPending}
            >
              Quizzes
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => onBundle.mutate(limit)}
              disabled={onBundle.isPending}
            >
              Student bundle
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-3 lg:grid-cols-[1fr_2fr]">
        <Card>
          <CardContent className="p-3">
            <h4 className="px-2 pt-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Recent runs
            </h4>
            {isLoading ? (
              <Skeleton className="mt-2 h-32 w-full" />
            ) : (
              <ul className="mt-2 space-y-1">
                {(data?.runs || []).map((r) => (
                  <li key={r.run_id}>
                    <button
                      onClick={() => setActiveRun(r.run_id)}
                      className={`block w-full rounded-md p-2 text-left text-xs hover:bg-muted ${activeRun === r.run_id ? "bg-muted" : ""}`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium">{r.type}</span>
                        <Badge variant="outline" className="text-[10px]">
                          {r.item_count} items
                        </Badge>
                      </div>
                      <div className="text-[11px] text-muted-foreground">
                        {r.label || "(unlabeled)"} · {formatRelative(r.created_at)}
                        {typeof r.avg_overall === "number" && (
                          <> · avg {(r.avg_overall * 100).toFixed(0)}%</>
                        )}
                      </div>
                    </button>
                  </li>
                ))}
                {data?.runs.length === 0 && (
                  <p className="px-2 py-4 text-center text-xs text-muted-foreground">
                    No runs yet.
                  </p>
                )}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-5">
            {activeRun ? (
              <RunDetail runId={activeRun} />
            ) : (
              <div className="flex flex-col items-center gap-2 py-12 text-sm text-muted-foreground">
                <FlaskConical className="h-8 w-8" />
                Pick a run to view scored items.
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function RunDetail({ runId }: { runId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-eval-run", runId],
    queryFn: () => api.adminEvalGetRun(runId),
  });
  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!data) return null;
  const r: EvalRun = data.run;
  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold">{r.label || r.type}</h3>
        <p className="text-xs text-muted-foreground">
          {r.item_count} items · triggered {formatRelative(r.created_at)}
          {r.triggered_by && ` by ${r.triggered_by}`}
        </p>
      </div>
      <div className="max-h-[60vh] space-y-2 overflow-y-auto">
        {data.items.map((it: EvalItem) => (
          <div
            key={it.id}
            className="rounded-md border border-border bg-surface-2 p-3 text-xs"
          >
            <div className="mb-1 flex items-center justify-between">
              <Badge
                variant={
                  it.score >= 0.8 ? "success" : it.score >= 0.5 ? "warning" : "danger"
                }
              >
                {Math.round(it.score * 100)}%
              </Badge>
            </div>
            <p className="line-clamp-3">
              <strong>Input:</strong> {it.input}
            </p>
            <p className="mt-1 line-clamp-3 text-muted-foreground">
              <strong>Output:</strong> {it.output}
            </p>
            {it.reasoning && (
              <p className="mt-1 line-clamp-3 italic text-muted-foreground">
                {it.reasoning}
              </p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
