"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { GraduationCap, Loader2, FlaskConical, Users } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ScoreRing } from "@/components/ui/score-ring";
import { EmptyState } from "@/components/ui/empty-state";
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

  const onStudentBundle = useMutation({
    mutationFn: (limit: number) => api.adminEvalRunStudentBundle({ limit }),
    onSuccess: (resp) => {
      toast.success(
        `Student bundle complete — ${resp.n_sub_runs} sub-run${resp.n_sub_runs === 1 ? "" : "s"}, avg ${Math.round((resp.avg_overall || 0) * 100)}%.`
      );
      qc.invalidateQueries({ queryKey: RUNS_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });
  const onTeacherBundle = useMutation({
    mutationFn: (limit: number) => api.adminEvalRunTeacherBundle({ limit }),
    onSuccess: (resp) => {
      toast.success(
        `Teacher bundle complete — ${resp.n_sub_runs} sub-run${resp.n_sub_runs === 1 ? "" : "s"}, avg ${Math.round((resp.avg_overall || 0) * 100)}%.`
      );
      qc.invalidateQueries({ queryKey: RUNS_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  const [limit, setLimit] = React.useState(20);
  const anyPending = onStudentBundle.isPending || onTeacherBundle.isPending;

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-4 p-5">
          <div>
            <h3 className="text-sm font-semibold">Run an evaluation</h3>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Each button bundles every relevant AI module for that role
              into a single batch — student picks up Q&amp;A · summaries
              · quizzes; teacher picks up short / long / MCQ / fill-in /
              true-false generations. Each sub-module becomes its own
              run in the list so you can spot which one is dragging the
              average down.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <Label htmlFor="sample-size">Sample size</Label>
              <Input
                id="sample-size"
                type="number"
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value) || 20)}
                className="w-24"
                min={1}
                max={200}
              />
            </div>
            <Button
              size="sm"
              onClick={() => onStudentBundle.mutate(limit)}
              disabled={anyPending}
            >
              {onStudentBundle.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <GraduationCap className="h-3.5 w-3.5" />
              )}
              Run student evals
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => onTeacherBundle.mutate(limit)}
              disabled={anyPending}
            >
              {onTeacherBundle.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Users className="h-3.5 w-3.5" />
              )}
              Run teacher evals
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
                  <li key={r.id}>
                    <button
                      onClick={() => setActiveRun(r.id)}
                      className={`block w-full rounded-md p-2 text-left text-xs hover:bg-muted ${activeRun === r.id ? "bg-muted" : ""}`}
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
                  <EmptyState
                    compact
                    title="No runs yet"
                    description="Trigger an evaluation above to populate this list."
                  />
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
              <EmptyState
                icon={<FlaskConical className="h-5 w-5" />}
                title="Pick a run"
                description="Select a run on the left to see its per-item scores and reasoning."
              />
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
  // avg_overall is stored as a 0..1 ratio; convert to a 0..100 pct for
  // the headline ring. Missing/undefined → null so we skip the ring.
  const avgPct =
    typeof r.avg_overall === "number" ? Math.round(r.avg_overall * 100) : null;
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-4">
        {avgPct !== null && (
          <ScoreRing value={avgPct} size={72} label="Avg score" />
        )}
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold">{r.label || r.type}</h3>
          <p className="text-xs text-muted-foreground">
            {r.item_count} items · triggered {formatRelative(r.created_at)}
            {r.triggered_by && ` by ${r.triggered_by}`}
          </p>
          {(typeof r.avg_faithfulness === "number" ||
            typeof r.avg_relevance === "number") && (
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              {typeof r.avg_faithfulness === "number" && (
                <span>
                  Faithfulness:{" "}
                  <span className="font-medium text-foreground tabular-nums">
                    {Math.round(r.avg_faithfulness * 100)}%
                  </span>
                </span>
              )}
              {typeof r.avg_relevance === "number" && (
                <span>
                  Relevance:{" "}
                  <span className="font-medium text-foreground tabular-nums">
                    {Math.round(r.avg_relevance * 100)}%
                  </span>
                </span>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="max-h-[60vh] space-y-2 overflow-y-auto">
        {data.items.map((it: EvalItem) => {
          // Backend may send `score_out_of_100` (0..100), `score` (0..1
          // ratio or 0..100 depending on the run type), or neither.
          // Normalize to a 0..100 number, or null if both are missing.
          const pct = normalizePct(it);
          return (
            <div
              key={it.id}
              className="rounded-md border border-border bg-surface-2 p-3 text-xs"
            >
              <div className="mb-1 flex items-center justify-between">
                {pct === null ? (
                  <Badge variant="outline">No score</Badge>
                ) : (
                  <Badge
                    variant={
                      pct >= 80 ? "success" : pct >= 50 ? "warning" : "danger"
                    }
                  >
                    {Math.round(pct)}%
                  </Badge>
                )}
              </div>
              <p className="line-clamp-3">
                <strong>Input:</strong>{" "}
                {it.input || (
                  <span className="text-muted-foreground">(empty)</span>
                )}
              </p>
              <p className="mt-1 line-clamp-3 text-muted-foreground">
                <strong>Output:</strong>{" "}
                {it.output || (
                  <span className="text-muted-foreground">(empty)</span>
                )}
              </p>
              {it.reasoning && (
                <p className="mt-1 line-clamp-3 italic text-muted-foreground">
                  {it.reasoning}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Convert whatever score field the backend sent into a 0..100 percentage.
 * Some run types emit `score_out_of_100` (already 0..100); others emit
 * `score` as a 0..1 ratio; legacy student-bundle records sometimes emit
 * `score` already on 0..100. Heuristic: any `score` value > 1 is
 * already a percentage. Returns null when neither field is a finite
 * number — caller shows "No score" instead of NaN%.
 */
function normalizePct(it: EvalItem): number | null {
  if (typeof it.score_out_of_100 === "number" && Number.isFinite(it.score_out_of_100)) {
    return it.score_out_of_100;
  }
  if (typeof it.score === "number" && Number.isFinite(it.score)) {
    return it.score <= 1 ? it.score * 100 : it.score;
  }
  return null;
}
