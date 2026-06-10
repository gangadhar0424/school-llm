"use client";

import * as React from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2, Upload, Wand2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import type {
  EvaluateAnswerResponse,
  GradingStandards,
  ParsedQuestion,
} from "@/lib/types";

// Radix forbids empty-string values on SelectItem (reserved for clearing
// the selection), so "None" gets a sentinel. The submit handler maps it
// back to "" before sending to the backend.
const SUBJECT_NONE = "__none__";
const SUBJECTS = [SUBJECT_NONE, "Math", "Science", "English", "Social", "Computer"];

export function AnswerEvaluator() {
  const [studentClass, setStudentClass] = React.useState<number>(5);
  const [subject, setSubject] = React.useState<string>(SUBJECT_NONE);
  // The sentinel is purely a Radix workaround; everything downstream
  // (overlay lookup, API submit, display label) wants an empty string
  // when the user picked "none".
  const cleanSubject = subject === SUBJECT_NONE ? "" : subject;

  const { data: standards } = useQuery({
    queryKey: ["grading-standards"],
    queryFn: api.getGradingStandards,
  });

  const activeBand = pickBand(standards, studentClass);
  const subjectOverlay = cleanSubject
    ? standards?.subjects?.[cleanSubject]?.extra_instructions
    : undefined;

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="grid gap-3 p-4 sm:grid-cols-2">
          <div>
            <Label>Student class</Label>
            <Select
              value={String(studentClass)}
              onValueChange={(v) => setStudentClass(Number(v))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Array.from({ length: 10 }, (_, i) => i + 1).map((c) => (
                  <SelectItem key={c} value={String(c)}>
                    {c}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label>Subject (optional overlay)</Label>
            <Select value={subject} onValueChange={setSubject}>
              <SelectTrigger>
                <SelectValue placeholder="None" />
              </SelectTrigger>
              <SelectContent>
                {SUBJECTS.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s === SUBJECT_NONE ? "— none —" : s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <details className="rounded-md border border-border bg-surface-2 p-3 text-xs">
        <summary className="cursor-pointer font-medium">
          📐 Grading rubric applied to evaluations
        </summary>
        <div className="mt-2 space-y-2 text-muted-foreground">
          {activeBand ? (
            <>
              <p>
                Band: <strong className="text-foreground">{activeBand.label || activeBand.band}</strong>{" "}
                · keyword pass ratio:{" "}
                {activeBand.keyword_pass_ratio ?? "—"} · vocab tolerance:{" "}
                {String(activeBand.vocab_tolerance ?? "—")}
              </p>
              {(activeBand.rubric_instructions || []).map((line, i) => (
                <p key={i}>· {line}</p>
              ))}
            </>
          ) : (
            <p>(no band matched)</p>
          )}
          {subjectOverlay && (
            <>
              <p className="font-semibold text-foreground">
                Subject overlay ({cleanSubject})
              </p>
              {subjectOverlay.map((s, i) => (
                <p key={i}>· {s}</p>
              ))}
            </>
          )}
        </div>
      </details>

      <Tabs defaultValue="manual">
        <TabsList className="grid grid-cols-2">
          <TabsTrigger value="manual">Manual entry</TabsTrigger>
          <TabsTrigger value="paste">Paste batch</TabsTrigger>
        </TabsList>
        <TabsContent value="manual" className="pt-4">
          <ManualEvaluator studentClass={studentClass} subject={cleanSubject} />
        </TabsContent>
        <TabsContent value="paste" className="pt-4">
          <PasteEvaluator studentClass={studentClass} subject={cleanSubject} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function pickBand(standards: GradingStandards | undefined, cls: number) {
  if (!standards?.bands) return null;
  for (const b of standards.bands) {
    const lo = b.class_min ?? -Infinity;
    const hi = b.class_max ?? Infinity;
    if (cls >= lo && cls <= hi) return b;
  }
  return standards.bands[0] || null;
}

// ── Manual ───────────────────────────────────────────────────────────────

function ManualEvaluator({
  studentClass,
  subject,
}: {
  studentClass: number;
  subject: string;
}) {
  const [question, setQuestion] = React.useState("");
  const [expected, setExpected] = React.useState("");
  const [keywords, setKeywords] = React.useState("");
  const [studentAnswer, setStudentAnswer] = React.useState("");
  const [result, setResult] = React.useState<EvaluateAnswerResponse | null>(null);

  const extract = useMutation({
    mutationFn: api.extractText,
    onSuccess: (data) => {
      setStudentAnswer(data.text || "");
      if (data.warning) toast.warning(data.warning);
      else toast.success(`Extracted ${data.char_count} chars`);
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  const evaluate = useMutation({
    mutationFn: () =>
      api.evaluateAnswer({
        question: question.trim() || undefined,
        expected_answer: expected.trim() || undefined,
        keywords: keywords
          .split(",")
          .map((k) => k.trim())
          .filter(Boolean),
        student_answer: studentAnswer,
        student_class: studentClass,
        subject: subject || null,
      }),
    onSuccess: (data) => setResult(data),
    onError: (e: ApiError) => toast.error(e.message),
  });

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <Label>Question</Label>
          <Textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={2}
          />
        </div>
        <div>
          <Label>Expected answer</Label>
          <Textarea
            value={expected}
            onChange={(e) => setExpected(e.target.value)}
            rows={2}
          />
        </div>
        <div className="sm:col-span-2">
          <Label>Keywords (comma-separated)</Label>
          <Input
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            placeholder="e.g. photosynthesis, chlorophyll"
          />
        </div>
        <div className="sm:col-span-2">
          <Label>Student answer</Label>
          <Textarea
            value={studentAnswer}
            onChange={(e) => setStudentAnswer(e.target.value)}
            rows={4}
          />
          <label className="mt-2 inline-flex cursor-pointer items-center gap-2 rounded-md border border-border bg-surface-2 px-3 py-1.5 text-xs hover:bg-muted">
            <Upload className="h-3.5 w-3.5" />
            {extract.isPending ? "Extracting…" : "Upload handwritten answer"}
            <Input
              type="file"
              accept=".pdf,image/*"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) extract.mutate(f);
                e.target.value = "";
              }}
              disabled={extract.isPending}
            />
          </label>
        </div>
      </div>
      <Button
        onClick={() => evaluate.mutate()}
        disabled={!studentAnswer.trim() || evaluate.isPending}
      >
        {evaluate.isPending ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" /> Evaluating…
          </>
        ) : (
          <>
            <Wand2 className="h-4 w-4" /> Evaluate answer
          </>
        )}
      </Button>
      {result && <EvalResultCard r={result} />}
    </div>
  );
}

// ── Paste batch ──────────────────────────────────────────────────────────

function PasteEvaluator({
  studentClass,
  subject,
}: {
  studentClass: number;
  subject: string;
}) {
  const [text, setText] = React.useState("");
  const [blocks, setBlocks] = React.useState<ParsedQuestion[]>([]);
  const [answers, setAnswers] = React.useState<Record<number, string>>({});
  const [results, setResults] = React.useState<
    Record<number, EvaluateAnswerResponse>
  >({});

  const parse = useMutation({
    mutationFn: () => api.parseQuestions(text),
    onSuccess: (data) => {
      setBlocks(data.blocks || []);
      setAnswers({});
      setResults({});
      toast.success(`Parsed ${data.blocks?.length || 0} block(s).`);
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  const evaluateAll = useMutation({
    mutationFn: async () => {
      const out: Record<number, EvaluateAnswerResponse> = {};
      for (let i = 0; i < blocks.length; i++) {
        const ans = (answers[i] || "").trim();
        if (!ans) continue;
        const b = blocks[i];
        try {
          out[i] = await api.evaluateAnswer({
            question: b.question,
            expected_answer: b.expected_answer,
            keywords: b.keywords,
            student_answer: ans,
            student_class: studentClass,
            target_class: b.target_class ?? null,
            subject: subject || b.subject || null,
          });
        } catch (e) {
          if (e instanceof ApiError) toast.error(`Q${i + 1}: ${e.message}`);
        }
      }
      return out;
    },
    onSuccess: (out) => {
      setResults(out);
      toast.success(`Scored ${Object.keys(out).length} answer(s).`);
    },
  });

  const avg =
    Object.values(results).length > 0
      ? Object.values(results).reduce((s, r) => s + (r.score_out_of_10 || 0), 0) /
        Object.values(results).length
      : null;

  return (
    <div className="space-y-3">
      <Label>Paste the &ldquo;Copyable text&rdquo; block</Label>
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={6}
        placeholder={`Q1. The capital of France is _______.\n    Answer: Paris\n    Keywords: capital, France\n\nQ2. …`}
      />
      <div className="flex gap-2">
        <Button onClick={() => parse.mutate()} disabled={!text.trim() || parse.isPending}>
          {parse.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            "Parse questions"
          )}
        </Button>
        {blocks.length > 0 && (
          <Button
            variant="ghost"
            onClick={() => {
              setBlocks([]);
              setAnswers({});
              setResults({});
            }}
          >
            Clear
          </Button>
        )}
      </div>

      {blocks.map((b, i) => (
        <Card key={i}>
          <CardContent className="space-y-2 p-4 text-sm">
            <p className="font-medium">
              Q{i + 1}. {b.question}
            </p>
            <p className="text-xs text-muted-foreground">
              Expected: {b.expected_answer || "—"}
            </p>
            {b.keywords && b.keywords.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Keywords: {b.keywords.join(", ")}
              </p>
            )}
            <Textarea
              rows={3}
              placeholder="Student answer"
              value={answers[i] || ""}
              onChange={(e) =>
                setAnswers((prev) => ({ ...prev, [i]: e.target.value }))
              }
            />
            {results[i] && <EvalResultCard r={results[i]} compact />}
          </CardContent>
        </Card>
      ))}

      {blocks.length > 0 && (
        <div className="flex items-center justify-between">
          {avg != null && (
            <Badge variant="outline">
              Average: {avg.toFixed(1)} / 10
            </Badge>
          )}
          <Button
            onClick={() => evaluateAll.mutate()}
            disabled={evaluateAll.isPending}
          >
            {evaluateAll.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Scoring…
              </>
            ) : (
              "Evaluate all answered"
            )}
          </Button>
        </div>
      )}
    </div>
  );
}

// ── Result card ──────────────────────────────────────────────────────────

function EvalResultCard({
  r,
  compact = false,
}: {
  r: EvaluateAnswerResponse;
  compact?: boolean;
}) {
  const s = r.score_out_of_10 || 0;
  const tone =
    s >= 7 ? "success" : s >= 4 ? "warning" : "danger";
  return (
    <div
      className={`mt-2 rounded-md border border-border bg-surface-2 p-3 text-xs ${compact ? "" : "border-primary/40"}`}
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">
          {s.toFixed(1)} / 10
          <Badge variant="outline" className="ml-2 text-[10px]">
            {r.method}
          </Badge>
          {r.grading_band_label && (
            <Badge variant="outline" className="ml-1 text-[10px]">
              {r.grading_band_label}
            </Badge>
          )}
        </p>
        <Badge variant={tone}>{Math.round((s / 10) * 100)}%</Badge>
      </div>
      <Progress value={(s / 10) * 100} className="mt-2 h-1.5" />

      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        {r.keyword_score && (
          <div>
            <p className="font-semibold">Keywords</p>
            <p className="text-muted-foreground">
              {r.keyword_score.matched_count ?? r.keyword_score.matched.length} /{" "}
              {r.keyword_score.total ?? r.keyword_score.matched.length + r.keyword_score.missed.length}{" "}
              · ratio {(r.keyword_score.ratio * 100).toFixed(0)}%
            </p>
            <div className="mt-1 flex flex-wrap gap-1">
              {r.keyword_score.matched.map((k) => (
                <span
                  key={`m-${k}`}
                  className="rounded-full bg-success/15 px-1.5 text-success"
                >
                  {k}
                </span>
              ))}
              {r.keyword_score.missed.map((k) => (
                <span
                  key={`x-${k}`}
                  className="rounded-full bg-danger/15 px-1.5 text-danger line-through"
                >
                  {k}
                </span>
              ))}
            </div>
          </div>
        )}
        {r.semantic_score && (
          <div>
            <p className="font-semibold">Semantic</p>
            <p className="text-muted-foreground">
              {(r.semantic_score.semantic_score_out_of_10 ?? r.semantic_score.score_out_of_10 ?? 0).toFixed(1)} /
              10
            </p>
          </div>
        )}
      </div>

      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        {r.correct_points?.length > 0 && (
          <Pane title="✅ Correct points" items={r.correct_points} tone="success" />
        )}
        {r.mistakes?.length > 0 && (
          <Pane title="❌ Mistakes" items={r.mistakes} tone="danger" />
        )}
        {r.improvements?.length > 0 && (
          <Pane title="💡 Improvements" items={r.improvements} tone="warning" />
        )}
        {r.correct_answer && (
          <div className="rounded-md border border-primary/40 bg-primary-chip p-2">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-primary">
              📖 Correct answer
            </p>
            <p className="whitespace-pre-wrap text-xs">{r.correct_answer}</p>
          </div>
        )}
      </div>
      {r.class_mismatch_warning && (
        <p className="mt-2 rounded-md bg-warning/15 px-2 py-1 text-[11px] text-warning">
          ⚠️ {r.class_mismatch_warning}
        </p>
      )}
    </div>
  );
}

function Pane({
  title,
  items,
  tone,
}: {
  title: string;
  items: string[];
  tone: "success" | "danger" | "warning";
}) {
  const toneClass =
    tone === "success"
      ? "border-success/40 bg-success/5"
      : tone === "danger"
        ? "border-danger/40 bg-danger/5"
        : "border-warning/40 bg-warning/5";
  return (
    <div className={`rounded-md border p-2 ${toneClass}`}>
      <p className="text-[10px] font-semibold uppercase tracking-wide">{title}</p>
      <ul className="ml-4 list-disc">
        {items.map((p, i) => (
          <li key={i}>{p}</li>
        ))}
      </ul>
    </div>
  );
}
