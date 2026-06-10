"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Loader2,
  Upload,
  XCircle,
  Lightbulb,
  ListChecks,
  BookOpenCheck,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { STUDENT_ASSIGNMENTS_KEY } from "../assignments-list";
import type { Submission, SubmissionAnswer } from "@/lib/types";

const ASSIGNMENT_KEY = (id: string) => ["student-assignment", id] as const;

export function AssignmentDetailClient({
  assignmentId,
}: {
  assignmentId: string;
}) {
  const qc = useQueryClient();
  const router = useRouter();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ASSIGNMENT_KEY(assignmentId),
    queryFn: () => api.studentAssignment(assignmentId),
  });

  // Local in-progress answers, keyed by question index. Persisted across
  // re-renders but not across reloads — assignments are short enough that
  // a hard reload restart is acceptable, and avoiding server round-trips
  // on every keystroke keeps the UI snappy.
  const [answers, setAnswers] = React.useState<Record<number, string>>({});

  const submit = useMutation({
    mutationFn: () => {
      const payload = Object.entries(answers)
        .filter(([, v]) => v.trim().length > 0)
        .map(([k, v]) => ({
          question_index: Number(k),
          student_answer: v.trim(),
        }));
      return api.submitAssignment(assignmentId, payload);
    },
    onSuccess: () => {
      toast.success("Assignment submitted! Loading feedback…");
      qc.invalidateQueries({ queryKey: ASSIGNMENT_KEY(assignmentId) });
      qc.invalidateQueries({ queryKey: STUDENT_ASSIGNMENTS_KEY });
      qc.invalidateQueries({ queryKey: ["student-progress"] });
      router.refresh();
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (isError) {
    const msg = error instanceof ApiError ? error.message : "Failed to load";
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-danger">
          {msg}
        </CardContent>
      </Card>
    );
  }
  if (!data) return null;

  const a = data.assignment;
  const submission = data.my_submission;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="space-y-2 p-5">
          <h1 className="text-xl font-semibold">{a.title}</h1>
          <p className="text-xs text-muted-foreground">
            {a.subject ? `${a.subject} · ` : ""}
            Class {a.class_section} · {a.questions.length} question
            {a.questions.length === 1 ? "" : "s"}
            {a.due_date && ` · Due: ${new Date(a.due_date).toLocaleString()}`}
          </p>
          {a.description && (
            <p className="text-sm text-muted-foreground">{a.description}</p>
          )}
        </CardContent>
      </Card>

      {submission ? (
        <SubmissionView submission={submission} questions={a.questions} />
      ) : (
        <>
          {a.questions.map((q, i) => (
            <QuestionCard
              key={i}
              index={i}
              question={q.question}
              marks={q.marks}
              value={answers[i] || ""}
              onChange={(v) => setAnswers((prev) => ({ ...prev, [i]: v }))}
            />
          ))}
          <div className="flex justify-end">
            <Button
              onClick={() => submit.mutate()}
              disabled={
                submit.isPending ||
                Object.values(answers).every((v) => v.trim().length === 0)
              }
              size="lg"
            >
              {submit.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Submitting &
                  grading…
                </>
              ) : (
                "📤 Submit assignment"
              )}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

// ── Single answer card with file-OCR support ─────────────────────────────

function QuestionCard({
  index,
  question,
  marks,
  value,
  onChange,
}: {
  index: number;
  question: string;
  marks: number;
  value: string;
  onChange: (v: string) => void;
}) {
  const extract = useMutation({
    mutationFn: api.extractText,
    onSuccess: (data) => {
      onChange(data.text || "");
      if (data.warning) {
        toast.warning(data.warning);
      } else {
        toast.success(`Extracted ${data.char_count} characters`);
      }
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-sm font-semibold">
            Q{index + 1}. {question}
          </h2>
          <Badge variant="outline" className="shrink-0 text-xs">
            {marks} mark{marks === 1 ? "" : "s"}
          </Badge>
        </div>

        <Textarea
          placeholder="Type your answer here…"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="min-h-32"
        />

        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex cursor-pointer items-center gap-2 rounded-md border border-border bg-surface-2 px-3 py-1.5 text-xs hover:bg-muted">
            <Upload className="h-3.5 w-3.5" />
            {extract.isPending ? "Extracting…" : "Upload handwritten answer"}
            <Input
              type="file"
              accept=".pdf,image/png,image/jpeg,image/jpg,image/webp,image/bmp"
              className="hidden"
              disabled={extract.isPending}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) extract.mutate(f);
                e.target.value = "";
              }}
            />
          </label>
          <p className="text-xs text-muted-foreground">
            We&apos;ll OCR the upload and paste the text into the box above —
            edit before submitting if anything looks off.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Submitted view with per-question feedback ────────────────────────────

function SubmissionView({
  submission,
  questions,
}: {
  submission: Submission;
  questions: { question: string; marks: number }[];
}) {
  const pct = Math.round(submission.percent || 0);
  const tone =
    pct >= 80
      ? "text-success"
      : pct >= 50
        ? "text-warning"
        : "text-danger";

  return (
    <>
      <Card>
        <CardContent className="p-5">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold">Auto-graded</h2>
              <p className="text-xs text-muted-foreground">
                Submitted{" "}
                {new Date(submission.submitted_at).toLocaleString()}. Final
                marks may change after teacher review.
              </p>
            </div>
            <div className="text-right">
              <div className={`text-3xl font-bold ${tone}`}>{pct}%</div>
              <div className="text-xs text-muted-foreground">
                {submission.total_score.toFixed(1)} / {submission.total_max}
              </div>
            </div>
          </div>
          <Progress value={pct} className="mt-3 h-2" />
        </CardContent>
      </Card>

      {submission.answers.map((a, i) => (
        <AnswerFeedbackCard
          key={i}
          questionText={questions[a.question_index]?.question ?? `Q${i + 1}`}
          answer={a}
        />
      ))}
    </>
  );
}

function AnswerFeedbackCard({
  questionText,
  answer,
}: {
  questionText: string;
  answer: SubmissionAnswer;
}) {
  const effectiveScore =
    answer.teacher_override?.score ?? answer.scaled_score ?? answer.ai_score ?? 0;
  const max = answer.marks ?? 10;
  const pct = max > 0 ? Math.round((effectiveScore / max) * 100) : 0;
  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex items-start justify-between gap-3">
          <h3 className="text-sm font-semibold">
            Q{answer.question_index + 1}. {questionText}
          </h3>
          <Badge
            variant={pct >= 80 ? "success" : pct >= 50 ? "warning" : "danger"}
          >
            {effectiveScore.toFixed(1)} / {max}
          </Badge>
        </div>
        <div className="rounded-md border border-border bg-surface-2 p-3 text-sm">
          <div className="mb-1 text-xs text-muted-foreground">Your answer</div>
          <p className="whitespace-pre-wrap">
            {answer.student_answer || (
              <span className="text-muted-foreground">(blank)</span>
            )}
          </p>
        </div>
        {answer.teacher_override && (
          <div className="rounded-md border border-primary/40 bg-primary-chip p-3 text-sm">
            <div className="mb-1 text-xs font-semibold text-primary">
              Teacher override · {answer.teacher_override.score.toFixed(1)} / {max}
            </div>
            {answer.teacher_override.comment && (
              <p className="text-xs">{answer.teacher_override.comment}</p>
            )}
          </div>
        )}
        {answer.feedback && (
          <FeedbackSections feedback={answer.feedback} />
        )}
        {answer.kw_summary && (
          <KeywordSummary kw={answer.kw_summary} />
        )}
      </CardContent>
    </Card>
  );
}

function FeedbackSections({
  feedback,
}: {
  feedback: NonNullable<SubmissionAnswer["feedback"]>;
}) {
  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
      {feedback.correct_points && feedback.correct_points.length > 0 && (
        <Section icon={<CheckCircle2 className="h-3 w-3" />} label="Correct points" tone="success">
          <ul className="ml-4 list-disc">
            {feedback.correct_points.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </Section>
      )}
      {feedback.mistakes && feedback.mistakes.length > 0 && (
        <Section icon={<XCircle className="h-3 w-3" />} label="Mistakes" tone="danger">
          <ul className="ml-4 list-disc">
            {feedback.mistakes.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </Section>
      )}
      {feedback.improvements && feedback.improvements.length > 0 && (
        <Section icon={<Lightbulb className="h-3 w-3" />} label="Improvements" tone="warning">
          <ul className="ml-4 list-disc">
            {feedback.improvements.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </Section>
      )}
      {feedback.correct_answer && (
        <Section icon={<BookOpenCheck className="h-3 w-3" />} label="Correct answer" tone="primary">
          <p className="whitespace-pre-wrap">{feedback.correct_answer}</p>
        </Section>
      )}
    </div>
  );
}

function Section({
  icon,
  label,
  tone,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  tone: "success" | "danger" | "warning" | "primary";
  children: React.ReactNode;
}) {
  const toneClass =
    tone === "success"
      ? "border-success/40 bg-success/5"
      : tone === "danger"
        ? "border-danger/40 bg-danger/5"
        : tone === "warning"
          ? "border-warning/40 bg-warning/5"
          : "border-primary/40 bg-primary-chip";
  return (
    <div className={`rounded-md border ${toneClass} p-3 text-xs`}>
      <div className="mb-1 flex items-center gap-1.5 font-semibold">
        {icon}
        {label}
      </div>
      {children}
    </div>
  );
}

function KeywordSummary({
  kw,
}: {
  kw: NonNullable<SubmissionAnswer["kw_summary"]>;
}) {
  const matched = kw.matched ?? [];
  const missed = kw.missed ?? [];
  if (matched.length === 0 && missed.length === 0) return null;
  return (
    <>
      <Separator />
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="text-muted-foreground">Keywords:</span>
        {matched.map((k) => (
          <span
            key={`m-${k}`}
            className="rounded-full bg-success/15 px-2 py-0.5 text-success"
          >
            <ListChecks className="mr-1 inline h-3 w-3" />
            {k}
          </span>
        ))}
        {missed.map((k) => (
          <span
            key={`mi-${k}`}
            className="rounded-full bg-danger/15 px-2 py-0.5 text-danger line-through"
          >
            {k}
          </span>
        ))}
      </div>
    </>
  );
}
