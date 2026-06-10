"use client";

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { Submission, SubmissionAnswer } from "@/lib/types";

export function TeacherAssignmentDetail({
  assignmentId,
}: {
  assignmentId: string;
}) {
  const key = ["teacher-assignment", assignmentId] as const;
  const { data, isLoading } = useQuery({
    queryKey: key,
    queryFn: () => api.teacherGetAssignment(assignmentId),
  });

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!data) return null;
  const a = data.assignment;

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-2 p-5">
          <div className="flex items-start justify-between gap-3">
            <h1 className="text-xl font-semibold">{a.title}</h1>
            <Badge variant={a.status === "published" ? "success" : "warning"}>
              {a.status}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            Class {a.class_section}
            {a.subject ? ` · ${a.subject}` : ""} · {a.questions.length} Q ·{" "}
            {a.submission_count ?? data.submissions.length} submissions
            {a.due_date && ` · Due ${new Date(a.due_date).toLocaleString()}`}
          </p>
          {a.description && (
            <p className="text-sm text-muted-foreground">{a.description}</p>
          )}
        </CardContent>
      </Card>

      <section>
        <h2 className="mb-2 text-sm font-semibold">Questions</h2>
        <div className="grid gap-2">
          {a.questions.map((q, i) => (
            <Card key={i}>
              <CardContent className="space-y-1 p-4 text-sm">
                <p className="font-medium">
                  Q{i + 1}. {q.question}{" "}
                  <Badge variant="outline" className="ml-2 text-[10px]">
                    {q.marks} mark{q.marks === 1 ? "" : "s"}
                  </Badge>
                  {q.question_type && (
                    <Badge variant="outline" className="ml-1 text-[10px]">
                      {q.question_type}
                    </Badge>
                  )}
                </p>
                {q.expected_answer && (
                  <p className="text-xs text-muted-foreground">
                    Expected: {q.expected_answer}
                  </p>
                )}
                {q.keywords && q.keywords.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    Keywords: {q.keywords.join(", ")}
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-sm font-semibold">
          Submissions ({data.submissions.length})
        </h2>
        {data.submissions.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              No submissions yet.
            </CardContent>
          </Card>
        ) : (
          data.submissions.map((s) => (
            <SubmissionCard key={s.id} sub={s} questions={a.questions} />
          ))
        )}
      </section>
    </div>
  );
}

function SubmissionCard({
  sub,
  questions,
}: {
  sub: Submission;
  questions: { question: string; marks: number }[];
}) {
  const [expanded, setExpanded] = React.useState(false);
  const pct = Math.round(sub.percent || 0);
  return (
    <Card className="mb-2">
      <CardContent className="p-4">
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex w-full items-center justify-between text-left"
        >
          <span className="text-sm font-medium">
            📝 {sub.student_email || sub.student_id}
          </span>
          <span className="flex items-center gap-2">
            <Badge variant={pct >= 80 ? "success" : pct >= 50 ? "warning" : "danger"}>
              {sub.total_score.toFixed(1)} / {sub.total_max} · {pct}%
            </Badge>
            <span className="text-xs text-muted-foreground">
              {expanded ? "▲" : "▼"}
            </span>
          </span>
        </button>
        {expanded && (
          <div className="mt-3 space-y-3 border-t border-border pt-3">
            {sub.answers.map((a) => (
              <AnswerRow
                key={a.question_index}
                submissionId={sub.id}
                a={a}
                qText={questions[a.question_index]?.question ?? ""}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AnswerRow({
  submissionId,
  a,
  qText,
}: {
  submissionId: string;
  a: SubmissionAnswer;
  qText: string;
}) {
  const qc = useQueryClient();
  const aiScore = a.scaled_score ?? a.ai_score ?? 0;
  const effective = a.teacher_override?.score ?? aiScore;
  const [score, setScore] = React.useState(effective.toFixed(1));
  const [comment, setComment] = React.useState(a.teacher_override?.comment || "");

  const save = useMutation({
    mutationFn: () =>
      api.teacherOverrideGrade(
        submissionId,
        a.question_index,
        Number(score),
        comment
      ),
    onSuccess: () => {
      toast.success(`Q${a.question_index + 1} overridden`);
      qc.invalidateQueries({ queryKey: ["teacher-assignment"] });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  return (
    <div className="rounded-md border border-border bg-surface-2 p-3 text-sm">
      <p className="font-medium">
        Q{a.question_index + 1}. {qText}
      </p>
      <div className="mt-1 text-xs">
        <span className="text-muted-foreground">Student:</span>{" "}
        {a.student_answer || <em>(blank)</em>}
      </div>
      <div className="mt-1 text-xs text-muted-foreground">
        AI score: {(a.ai_score ?? 0).toFixed(1)} / 10 ·{" "}
        scaled: {(a.scaled_score ?? 0).toFixed(1)} / {a.marks}{" "}
        ({a.ai_method || "unknown"})
      </div>
      {a.teacher_override && (
        <div className="mt-1 text-xs text-primary">
          Teacher override active · {a.teacher_override.score.toFixed(1)} / 10
          {a.teacher_override.comment && ` · "${a.teacher_override.comment}"`}
        </div>
      )}
      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-[100px_1fr_auto]">
        <Input
          type="number"
          min={0}
          max={10}
          step={0.1}
          value={score}
          onChange={(e) => setScore(e.target.value)}
          className="h-8"
        />
        <Input
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Comment (optional)"
          className="h-8"
        />
        <Button
          size="sm"
          onClick={() => save.mutate()}
          disabled={save.isPending}
        >
          {save.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            "Save"
          )}
        </Button>
      </div>
    </div>
  );
}
