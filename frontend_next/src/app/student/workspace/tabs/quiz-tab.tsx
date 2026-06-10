"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, RotateCcw, Sparkles, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { USAGE_QUERY_KEY } from "@/components/dashboard/usage-card";
import type { QuizQuestion } from "@/lib/types";
import { cn } from "@/lib/utils";

const TYPES = [
  { value: "mcq", label: "Multiple choice" },
  { value: "true-false", label: "True / False" },
  { value: "fill-in-blank", label: "Fill in the blank" },
  { value: "short-answer", label: "Short answer" },
] as const;
const DIFFICULTIES = ["basic", "medium", "hard"] as const;

function mcqOptions(
  q: QuizQuestion
): { key: string; value: string }[] {
  const opts = q.options;
  if (!opts) return [];
  if (Array.isArray(opts)) {
    return opts.map((v, i) => ({
      key: String.fromCharCode(65 + i),
      value: v,
    }));
  }
  return Object.entries(opts)
    .filter(([, v]) => v && String(v).trim().length > 0)
    .map(([k, v]) => ({ key: k, value: String(v) }));
}

function normalize(s: string): string {
  return (s || "").trim().toLowerCase();
}

function isCorrect(q: QuizQuestion, given: string): boolean {
  const expected = normalize(q.expected_answer || "");
  if (!expected) return false;
  if (q.question_type === "mcq" || q.question_type === "true-false") {
    return normalize(given) === expected;
  }
  // For text answers, the backend evaluation is more nuanced — for the
  // quick auto-grade in the quiz UI, accept exact or substring matches.
  const g = normalize(given);
  return g.length > 0 && (g === expected || expected.includes(g) || g.includes(expected));
}

export function QuizTab({ pdfId }: { pdfId: string }) {
  const qc = useQueryClient();
  const [numQuestions, setNumQuestions] = React.useState(5);
  const [difficulty, setDifficulty] = React.useState<string>("medium");
  const [qType, setQType] = React.useState<string>("mcq");
  const [topic, setTopic] = React.useState("");

  const [questions, setQuestions] = React.useState<QuizQuestion[]>([]);
  const [answers, setAnswers] = React.useState<Record<number, string>>({});
  const [submitted, setSubmitted] = React.useState(false);
  const [score, setScore] = React.useState<{ s: number; t: number } | null>(
    null
  );
  const restoredOnceRef = React.useRef<string | null>(null);

  // Restore in-progress quiz on first load for this PDF.
  React.useEffect(() => {
    if (restoredOnceRef.current === pdfId) return;
    restoredOnceRef.current = pdfId;
    setQuestions([]);
    setAnswers({});
    setSubmitted(false);
    setScore(null);
    api
      .getActiveQuiz(pdfId)
      .then((data) => {
        if (data && data.questions?.length) {
          setQuestions(data.questions);
          setAnswers(data.answers || {});
          setQType(data.question_type || "mcq");
          setDifficulty(data.difficulty || "medium");
          toast.info("📝 Restored your in-progress quiz");
        }
      })
      .catch(() => {
        // Non-fatal — no active quiz.
      });
  }, [pdfId]);

  const generate = useMutation({
    mutationFn: () =>
      api.generateQuiz({
        pdf_url: pdfId,
        num_questions: numQuestions,
        difficulty,
        question_type: qType,
        search_query: topic.trim() || undefined,
      }),
    onSuccess: (data) => {
      setQuestions(data.questions);
      setAnswers({});
      setSubmitted(false);
      setScore(null);
      qc.invalidateQueries({ queryKey: USAGE_QUERY_KEY });
      // Persist so a reload doesn't lose progress.
      api
        .saveActiveQuiz({
          pdf_id: pdfId,
          questions: data.questions,
          question_type: qType,
          difficulty,
          answers: {},
        })
        .catch(() => {});
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  const submit = useMutation({
    mutationFn: () => {
      let s = 0;
      for (let i = 0; i < questions.length; i++) {
        if (isCorrect(questions[i], answers[i] || "")) s++;
      }
      const t = questions.length;
      setScore({ s, t });
      setSubmitted(true);
      return api.saveQuizAttempt({
        pdf_id: pdfId,
        questions,
        answers,
        score: s,
        total: t,
        question_type: qType,
        difficulty,
      });
    },
    onSuccess: () => {
      api.discardActiveQuiz(pdfId).catch(() => {});
      qc.invalidateQueries({ queryKey: ["history-quizzes"] });
    },
    onError: (e: ApiError) => toast.error(`Could not save attempt: ${e.message}`),
  });

  const restart = () => {
    if (!confirm("Discard this quiz and start over?")) return;
    setQuestions([]);
    setAnswers({});
    setSubmitted(false);
    setScore(null);
    api.discardActiveQuiz(pdfId).catch(() => {});
  };

  return (
    <div className="space-y-4">
      {/* Settings */}
      <Card>
        <CardContent className="grid gap-3 p-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <Label htmlFor="qcount">Questions</Label>
            <Input
              id="qcount"
              type="number"
              min={1}
              max={15}
              value={numQuestions}
              onChange={(e) =>
                setNumQuestions(
                  Math.max(1, Math.min(15, Number(e.target.value) || 5))
                )
              }
            />
          </div>
          <div>
            <Label htmlFor="qdiff">Difficulty</Label>
            <Select value={difficulty} onValueChange={setDifficulty}>
              <SelectTrigger id="qdiff">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DIFFICULTIES.map((d) => (
                  <SelectItem key={d} value={d}>
                    {d.charAt(0).toUpperCase() + d.slice(1)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="qtype">Question type</Label>
            <Select value={qType} onValueChange={setQType}>
              <SelectTrigger id="qtype">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TYPES.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div>
            <Label htmlFor="qtopic">Topic (optional)</Label>
            <Input
              id="qtopic"
              placeholder="e.g. chapter 3"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
            />
          </div>
        </CardContent>
        <CardContent className="flex justify-end gap-2 px-4 pb-4 pt-0">
          {questions.length > 0 && !submitted && (
            <Button variant="outline" onClick={restart}>
              <RotateCcw className="h-4 w-4" />
              Restart
            </Button>
          )}
          <Button
            onClick={() => generate.mutate()}
            disabled={generate.isPending}
          >
            {generate.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Generating…
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                Generate quiz
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Questions or results */}
      {questions.length === 0 && !generate.isPending && (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Configure settings above and click <em>Generate quiz</em>.
          </CardContent>
        </Card>
      )}

      {questions.length > 0 && !submitted && (
        <Card>
          <CardContent className="space-y-4 p-5">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold">
                {questions.length} questions
              </h3>
              <div className="flex gap-2">
                <Badge variant="outline">{difficulty}</Badge>
                <Badge variant="outline">{qType}</Badge>
              </div>
            </div>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (Object.values(answers).filter((v) => v.trim()).length === 0) {
                  toast.error("Answer at least one question.");
                  return;
                }
                submit.mutate();
              }}
              className="space-y-4"
            >
              {questions.map((q, i) => (
                <QuestionBlock
                  key={i}
                  index={i}
                  q={q}
                  value={answers[i] || ""}
                  onChange={(v) => {
                    setAnswers((prev) => {
                      const next = { ...prev, [i]: v };
                      // Persist as we go so a reload restores answers too.
                      api
                        .saveActiveQuiz({
                          pdf_id: pdfId,
                          questions,
                          question_type: qType,
                          difficulty,
                          answers: next,
                        })
                        .catch(() => {});
                      return next;
                    });
                  }}
                />
              ))}
              <Button type="submit" size="lg" disabled={submit.isPending}>
                {submit.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Grading…
                  </>
                ) : (
                  "✅ Submit & check answers"
                )}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {submitted && score && (
        <ResultsView
          questions={questions}
          answers={answers}
          score={score}
          onTryAgain={() => {
            setQuestions([]);
            setAnswers({});
            setSubmitted(false);
            setScore(null);
          }}
        />
      )}
    </div>
  );
}

function QuestionBlock({
  index,
  q,
  value,
  onChange,
}: {
  index: number;
  q: QuizQuestion;
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div className="rounded-md border border-border bg-surface-2 p-4">
      <p className="mb-3 text-sm font-medium">
        Q{index + 1}. {q.question}
      </p>
      {q.question_type === "mcq" ? (
        <RadioGroup value={value} onValueChange={onChange}>
          {mcqOptions(q).map((opt) => (
            <label
              key={opt.key}
              className="flex cursor-pointer items-center gap-2 rounded-md p-2 hover:bg-muted"
            >
              <RadioGroupItem value={opt.key} id={`q${index}-${opt.key}`} />
              <span className="text-sm">
                <strong>{opt.key}.</strong> {opt.value}
              </span>
            </label>
          ))}
        </RadioGroup>
      ) : q.question_type === "true-false" ? (
        <RadioGroup value={value} onValueChange={onChange} className="flex gap-4">
          {["True", "False"].map((opt) => (
            <label
              key={opt}
              className="flex cursor-pointer items-center gap-2"
            >
              <RadioGroupItem value={opt} id={`q${index}-${opt}`} />
              <span className="text-sm">{opt}</span>
            </label>
          ))}
        </RadioGroup>
      ) : (
        <Input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Type your answer"
        />
      )}
    </div>
  );
}

function ResultsView({
  questions,
  answers,
  score,
  onTryAgain,
}: {
  questions: QuizQuestion[];
  answers: Record<number, string>;
  score: { s: number; t: number };
  onTryAgain: () => void;
}) {
  const pct = Math.round((score.s / score.t) * 100);
  const tone =
    pct >= 80 ? "text-success" : pct >= 50 ? "text-warning" : "text-danger";
  const blurb =
    pct >= 80
      ? "🎉 Excellent!"
      : pct >= 50
        ? "👍 Good job!"
        : "📖 Keep studying!";
  return (
    <div className="space-y-3">
      <Card>
        <CardContent className="p-5 text-center">
          <div className={cn("text-5xl font-bold", tone)}>{score.s} / {score.t}</div>
          <div className="mt-1 text-base font-medium">{blurb}</div>
          <Progress value={pct} className="mt-3 h-2" />
          <div className="mt-2 text-xs text-muted-foreground">
            Score: {pct}%
          </div>
        </CardContent>
      </Card>

      {questions.map((q, i) => {
        const given = answers[i] || "";
        const correct = isCorrect(q, given);
        return (
          <Card key={i}>
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-medium">
                  Q{i + 1}. {q.question}
                </p>
                <Badge variant={correct ? "success" : "danger"}>
                  {correct ? "✓" : "✗"}
                </Badge>
              </div>
              <div className="mt-3 grid gap-2 text-xs">
                <div>
                  <span className="text-muted-foreground">Your answer:</span>{" "}
                  <span className={cn("font-medium", correct ? "text-success" : "text-danger")}>
                    {given || "(blank)"}
                  </span>
                </div>
                {!correct && q.expected_answer && (
                  <div>
                    <span className="text-muted-foreground">Correct answer:</span>{" "}
                    <span className="font-medium text-success">{q.expected_answer}</span>
                  </div>
                )}
                {q.explanation && (
                  <p className="text-muted-foreground">💡 {q.explanation}</p>
                )}
              </div>
            </CardContent>
          </Card>
        );
      })}

      <div className="flex justify-end">
        <Button variant="outline" onClick={onTryAgain}>
          <Trash2 className="h-4 w-4" />
          Try another quiz
        </Button>
      </div>
    </div>
  );
}
