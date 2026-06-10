"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Edit,
  Loader2,
  Plus,
  Save,
  Send,
  Sparkles,
  Trash2,
  Wand2,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogClose,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { USAGE_QUERY_KEY } from "@/components/dashboard/usage-card";
import { TEACHER_ASSIGNMENTS_KEY } from "../home-client";
import type { QuizQuestion } from "@/lib/types";

const ALL_SUBJECTS = ["Math", "Science", "English", "Social", "Computer"];
const TYPES = [
  "mcq",
  "true-false",
  "fill-in-blank",
  "short-answer",
  "long-answer",
];

export function NewAssignmentClient({
  assignedClasses,
  subjectsTaught,
}: {
  assignedClasses: string[];
  subjectsTaught: string[];
}) {
  const classes = assignedClasses.length > 0 ? assignedClasses : [];
  const subjects = subjectsTaught.length > 0 ? subjectsTaught : ALL_SUBJECTS;

  const [mode, setMode] = React.useState<null | "manual" | "ai">(null);
  const [title, setTitle] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [classSection, setClassSection] = React.useState(classes[0] || "");
  const [subject, setSubject] = React.useState(subjects[0] || "");
  const [dueDate, setDueDate] = React.useState("");
  const [questions, setQuestions] = React.useState<QuizQuestion[]>([]);
  const router = useRouter();
  const qc = useQueryClient();

  const create = useMutation({
    mutationFn: (status: "draft" | "published") =>
      api.teacherCreateAssignment({
        title: title.trim(),
        description: description.trim(),
        class_section: classSection,
        subject: subject || null,
        questions,
        due_date: dueDate ? new Date(dueDate).toISOString() : null,
        status,
      }),
    onSuccess: (resp, status) => {
      toast.success(
        status === "published" ? "📤 Published!" : "💾 Saved as draft."
      );
      qc.invalidateQueries({ queryKey: TEACHER_ASSIGNMENTS_KEY });
      setTitle("");
      setDescription("");
      setQuestions([]);
      setMode(null);
      router.push(`/teacher/assignments/${resp.id}`);
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  if (!mode) {
    return (
      <Card>
        <CardContent className="space-y-4 p-6">
          {questions.length > 0 && (
            <div className="rounded-md border border-primary/40 bg-primary-chip p-3 text-xs">
              You have <strong>{questions.length}</strong> question
              {questions.length === 1 ? "" : "s"} already added — pick a mode to
              keep building.
            </div>
          )}
          <p className="text-sm font-medium">How do you want to build this?</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <ModeCard
              onPick={() => setMode("manual")}
              icon="✏️"
              title="Manual entry"
              body="Type each question yourself. Best for short, hand-crafted sets."
            />
            <ModeCard
              onPick={() => setMode("ai")}
              icon="🤖"
              title="Use AI"
              body="Generate quiz items or a multi-section question paper from a PDF."
            />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="space-y-3 p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">
              {mode === "manual" ? "✏️ Manual entry" : "🤖 Use AI"}
            </h3>
            <Button variant="ghost" size="sm" onClick={() => setMode(null)}>
              ↺ Change mode
            </Button>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label>Title</Label>
              <Input value={title} onChange={(e) => setTitle(e.target.value)} />
            </div>
            <div>
              <Label>Class</Label>
              <Select value={classSection} onValueChange={setClassSection}>
                <SelectTrigger>
                  <SelectValue placeholder="Pick a class" />
                </SelectTrigger>
                <SelectContent>
                  {classes.length === 0 && (
                    <div className="px-3 py-2 text-xs text-muted-foreground">
                      No assigned classes. Ask an admin to assign you classes.
                    </div>
                  )}
                  {classes.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Subject</Label>
              <Select value={subject} onValueChange={setSubject}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {subjects.map((s) => (
                    <SelectItem key={s} value={s}>
                      {s}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="due">Due date / time</Label>
              <Input
                id="due"
                type="datetime-local"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
              />
            </div>
            <div className="sm:col-span-2">
              <Label>Description</Label>
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {mode === "manual" ? (
        <ManualBuilder
          onAdd={(q) => setQuestions((prev) => [...prev, q])}
        />
      ) : (
        <AIBuilder
          subject={subject}
          classSection={classSection}
          onImport={(qs) => setQuestions((prev) => [...prev, ...qs])}
        />
      )}

      <Card>
        <CardContent className="space-y-3 p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">
              Questions in this assignment ({questions.length})
            </h3>
            {questions.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  if (confirm("Clear all questions?")) setQuestions([]);
                }}
                className="text-danger hover:bg-danger/10"
              >
                Clear all
              </Button>
            )}
          </div>
          {questions.length === 0 ? (
            <p className="py-6 text-center text-xs text-muted-foreground">
              Add questions above to populate this list.
            </p>
          ) : (
            questions.map((q, i) => (
              <QuestionRow
                key={i}
                q={q}
                index={i}
                onEdit={(next) =>
                  setQuestions((prev) =>
                    prev.map((qq, idx) => (idx === i ? next : qq))
                  )
                }
                onRemove={() =>
                  setQuestions((prev) => prev.filter((_, idx) => idx !== i))
                }
              />
            ))
          )}
        </CardContent>
      </Card>

      <div className="flex flex-wrap justify-end gap-2">
        <Button
          variant="outline"
          disabled={
            create.isPending ||
            !title.trim() ||
            !classSection ||
            questions.length === 0
          }
          onClick={() => create.mutate("draft")}
        >
          {create.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Save as draft
        </Button>
        <Button
          disabled={
            create.isPending ||
            !title.trim() ||
            !classSection ||
            questions.length === 0
          }
          onClick={() => create.mutate("published")}
        >
          {create.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Send className="h-4 w-4" />
          )}
          Publish now
        </Button>
      </div>
    </div>
  );
}

function ModeCard({
  onPick,
  icon,
  title,
  body,
}: {
  onPick: () => void;
  icon: string;
  title: string;
  body: string;
}) {
  return (
    <button
      onClick={onPick}
      className="rounded-xl border border-border bg-surface-2 p-5 text-left transition-colors hover:border-primary"
    >
      <div className="text-3xl">{icon}</div>
      <div className="mt-2 text-base font-semibold">{title}</div>
      <p className="mt-1 text-xs text-muted-foreground">{body}</p>
    </button>
  );
}

// ── Manual ───────────────────────────────────────────────────────────────

function ManualBuilder({ onAdd }: { onAdd: (q: QuizQuestion) => void }) {
  const [question, setQuestion] = React.useState("");
  const [type, setType] = React.useState<string>("short-answer");
  const [marks, setMarks] = React.useState(5);
  const [expected, setExpected] = React.useState("");
  const [keywords, setKeywords] = React.useState("");
  const [options, setOptions] = React.useState<string[]>(["", "", "", ""]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return toast.error("Question is required.");
    if (!expected.trim() && type !== "mcq")
      return toast.error("Expected answer is required.");
    if (type === "mcq" && options.some((o) => !o.trim()))
      return toast.error("All 4 MCQ options are required.");

    const q: QuizQuestion = {
      question: question.trim(),
      question_type: type,
      marks,
      expected_answer: expected.trim() || (type === "mcq" ? "A" : ""),
      keywords: keywords
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean),
    };
    if (type === "mcq") {
      q.options = options.map((o) => o.trim());
    }
    onAdd(q);
    toast.success("Added.");
    setQuestion("");
    setExpected("");
    setKeywords("");
    setOptions(["", "", "", ""]);
  };

  return (
    <Card>
      <CardContent>
        <form onSubmit={submit} className="space-y-3 p-1">
          <h4 className="text-sm font-semibold">Add a question</h4>
          <div>
            <Label>Question</Label>
            <Textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={2}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <Label>Type</Label>
              <Select value={type} onValueChange={setType}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TYPES.map((t) => (
                    <SelectItem key={t} value={t}>
                      {t}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Marks</Label>
              <Input
                type="number"
                min={1}
                max={100}
                value={marks}
                onChange={(e) =>
                  setMarks(Math.max(1, Math.min(100, Number(e.target.value) || 1)))
                }
              />
            </div>
          </div>
          {type === "mcq" && (
            <div className="grid gap-2 sm:grid-cols-2">
              {options.map((opt, i) => (
                <div key={i}>
                  <Label>Option {String.fromCharCode(65 + i)}</Label>
                  <Input
                    value={opt}
                    onChange={(e) =>
                      setOptions((prev) =>
                        prev.map((o, idx) => (idx === i ? e.target.value : o))
                      )
                    }
                  />
                </div>
              ))}
            </div>
          )}
          <div>
            <Label>Expected answer</Label>
            <Textarea
              value={expected}
              onChange={(e) => setExpected(e.target.value)}
              rows={2}
              placeholder={
                type === "mcq"
                  ? "Use the letter, e.g. A"
                  : "Model answer used by the AI grader"
              }
            />
          </div>
          <div>
            <Label>Keywords (comma-separated)</Label>
            <Input
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              placeholder="photosynthesis, chlorophyll, sunlight"
            />
          </div>
          <Button type="submit" size="sm">
            <Plus className="h-4 w-4" />
            Add this question
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

// ── AI ───────────────────────────────────────────────────────────────────

function AIBuilder({
  subject,
  classSection,
  onImport,
}: {
  subject: string;
  classSection: string;
  onImport: (qs: QuizQuestion[]) => void;
}) {
  const { data: pdfsData } = useQuery({
    queryKey: ["my-pdfs"],
    queryFn: () => api.myPdfs(100),
  });
  const pdfs = React.useMemo(() => pdfsData?.pdfs ?? [], [pdfsData]);
  const [pickedPdfId, setPickedPdfId] = React.useState<string | null>(null);
  // Derive the active PDF: user's pick wins, otherwise first available.
  const pdfId = pickedPdfId ?? pdfs[0]?.pdf_identifier ?? "";
  const targetClass = classSection
    ? Number(classSection.replace(/[A-Z]/gi, ""))
    : null;

  if (pdfs.length === 0) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Upload at least one PDF (from the Home tab on a student/admin
          account, or your own) to use the AI builder.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label>Source PDF</Label>
            <Select value={pdfId} onValueChange={setPickedPdfId}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {pdfs.map((p) => (
                  <SelectItem
                    key={p.pdf_identifier}
                    value={p.pdf_identifier}
                  >
                    📄 {p.filename}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="text-xs text-muted-foreground">
            Generated questions target class{" "}
            <strong className="text-foreground">
              {targetClass ?? "—"}
            </strong>
            {subject && (
              <>
                {" · "}subject{" "}
                <strong className="text-foreground">{subject}</strong>
              </>
            )}
            .
          </div>
        </div>

        <Tabs defaultValue="short">
          <TabsList className="grid grid-cols-4">
            <TabsTrigger value="short">📝 Short/Long</TabsTrigger>
            <TabsTrigger value="mcq">🎲 MCQ</TabsTrigger>
            <TabsTrigger value="blank">✏️ Fill-blank</TabsTrigger>
            <TabsTrigger value="paper">📜 Question paper</TabsTrigger>
          </TabsList>

          <TabsContent value="short" className="pt-3">
            <QuizGenForm
              kinds={[
                { value: "short-answer", label: "Short answer" },
                { value: "long-answer", label: "Long answer" },
              ]}
              pdfId={pdfId}
              subject={subject}
              targetClass={targetClass}
              onImport={onImport}
              defaultMarks={(t) => (t === "long-answer" ? 10 : 5)}
            />
          </TabsContent>
          <TabsContent value="mcq" className="pt-3">
            <QuizGenForm
              kinds={[{ value: "mcq", label: "MCQ" }]}
              pdfId={pdfId}
              subject={subject}
              targetClass={targetClass}
              onImport={onImport}
              defaultMarks={() => 2}
            />
          </TabsContent>
          <TabsContent value="blank" className="pt-3">
            <QuizGenForm
              kinds={[{ value: "fill-in-blank", label: "Fill in the blank" }]}
              pdfId={pdfId}
              subject={subject}
              targetClass={targetClass}
              onImport={onImport}
              defaultMarks={() => 2}
            />
          </TabsContent>
          <TabsContent value="paper" className="pt-3">
            <QuestionPaperForm
              pdfId={pdfId}
              subject={subject}
              targetClass={targetClass}
              onImport={onImport}
            />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

function QuizGenForm({
  kinds,
  pdfId,
  subject,
  targetClass,
  onImport,
  defaultMarks,
}: {
  kinds: { value: string; label: string }[];
  pdfId: string;
  subject: string;
  targetClass: number | null;
  onImport: (qs: QuizQuestion[]) => void;
  defaultMarks: (type: string) => number;
}) {
  const qc = useQueryClient();
  const [type, setType] = React.useState(kinds[0].value);
  const [count, setCount] = React.useState(5);
  const [difficulty, setDifficulty] = React.useState("medium");
  const [topic, setTopic] = React.useState("");

  const gen = useMutation({
    mutationFn: () =>
      api.generateQuiz({
        pdf_url: pdfId,
        num_questions: count,
        difficulty,
        question_type: type,
        search_query: topic.trim() || undefined,
        target_class: targetClass,
        subject: subject || undefined,
      }),
    onSuccess: (data) => {
      const items = (data.questions || []).map((q) => ({
        ...q,
        marks: q.marks ?? defaultMarks(q.question_type || type),
      }));
      onImport(items);
      qc.invalidateQueries({ queryKey: USAGE_QUERY_KEY });
      toast.success(`Imported ${items.length} questions.`);
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-4">
        {kinds.length > 1 && (
          <div>
            <Label>Mode</Label>
            <Select value={type} onValueChange={setType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {kinds.map((k) => (
                  <SelectItem key={k.value} value={k.value}>
                    {k.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div>
          <Label>Count</Label>
          <Input
            type="number"
            min={1}
            max={15}
            value={count}
            onChange={(e) =>
              setCount(Math.max(1, Math.min(15, Number(e.target.value) || 5)))
            }
          />
        </div>
        <div>
          <Label>Difficulty</Label>
          <Select value={difficulty} onValueChange={setDifficulty}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {["basic", "medium", "hard"].map((d) => (
                <SelectItem key={d} value={d}>
                  {d}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="sm:col-span-2">
          <Label>Topic (optional)</Label>
          <Input value={topic} onChange={(e) => setTopic(e.target.value)} />
        </div>
      </div>
      <Button onClick={() => gen.mutate()} disabled={gen.isPending}>
        {gen.isPending ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" /> Generating…
          </>
        ) : (
          <>
            <Sparkles className="h-4 w-4" /> Generate & import
          </>
        )}
      </Button>
    </div>
  );
}

function QuestionPaperForm({
  pdfId,
  subject,
  targetClass,
  onImport,
}: {
  pdfId: string;
  subject: string;
  targetClass: number | null;
  onImport: (qs: QuizQuestion[]) => void;
}) {
  const qc = useQueryClient();
  const [topic, setTopic] = React.useState("");
  const [difficulty, setDifficulty] = React.useState("medium");
  const [mcq, setMcq] = React.useState(5);
  const [shortA, setShortA] = React.useState(3);
  const [longA, setLongA] = React.useState(2);
  const [fib, setFib] = React.useState(3);
  const [tf, setTf] = React.useState(3);

  const total = mcq + shortA + longA + fib + tf;
  const gen = useMutation({
    mutationFn: () =>
      api.teacherGenerateQuestionPaper({
        pdf_url: pdfId,
        topic: topic.trim(),
        difficulty,
        mcq,
        short_answer: shortA,
        long_answer: longA,
        fill_in_blank: fib,
        true_false: tf,
        target_class: targetClass,
        subject: subject || undefined,
      }),
    onSuccess: (data) => {
      onImport(data.questions);
      qc.invalidateQueries({ queryKey: USAGE_QUERY_KEY });
      if (data.sections_failed?.length) {
        toast.warning(
          `Imported ${data.questions.length}, but ${data.sections_failed.length} section(s) failed.`
        );
      } else {
        toast.success(`Imported ${data.questions.length} questions.`);
      }
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  return (
    <div className="space-y-3">
      <div>
        <Label>Topic / unit</Label>
        <Input value={topic} onChange={(e) => setTopic(e.target.value)} />
      </div>
      <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {[
          { label: "MCQ", v: mcq, set: setMcq },
          { label: "Short", v: shortA, set: setShortA },
          { label: "Long", v: longA, set: setLongA },
          { label: "Fill-blank", v: fib, set: setFib },
          { label: "True/False", v: tf, set: setTf },
        ].map((row) => (
          <div key={row.label}>
            <Label>{row.label}</Label>
            <Input
              type="number"
              min={0}
              max={25}
              value={row.v}
              onChange={(e) =>
                row.set(Math.max(0, Math.min(25, Number(e.target.value) || 0)))
              }
            />
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between">
        <Badge variant="outline">Total: {total}</Badge>
        <div className="flex gap-2">
          <Select value={difficulty} onValueChange={setDifficulty}>
            <SelectTrigger className="h-8 w-32">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {["basic", "medium", "hard"].map((d) => (
                <SelectItem key={d} value={d}>
                  {d}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            disabled={gen.isPending || total === 0 || !topic.trim()}
            onClick={() => gen.mutate()}
          >
            {gen.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Building paper…
              </>
            ) : (
              <>
                <Wand2 className="h-4 w-4" /> Generate paper
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}

function QuestionRow({
  q,
  index,
  onEdit,
  onRemove,
}: {
  q: QuizQuestion;
  index: number;
  onEdit: (next: QuizQuestion) => void;
  onRemove: () => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [draft, setDraft] = React.useState<QuizQuestion>(q);
  return (
    <div className="rounded-md border border-border bg-surface-2 p-3 text-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-medium">
            Q{index + 1}. {q.question}
          </p>
          <div className="mt-1 flex flex-wrap gap-1">
            <Badge variant="outline" className="text-[10px]">
              {q.question_type || "—"}
            </Badge>
            <Badge variant="outline" className="text-[10px]">
              {q.marks ?? "—"} marks
            </Badge>
            {q.target_class != null && (
              <Badge variant="outline" className="text-[10px]">
                Class {q.target_class}
              </Badge>
            )}
            {q.subject && (
              <Badge variant="outline" className="text-[10px]">
                {q.subject}
              </Badge>
            )}
          </div>
          {q.expected_answer && (
            <p className="mt-1 text-xs text-muted-foreground">
              Expected: {q.expected_answer}
            </p>
          )}
        </div>
        <div className="flex gap-1">
          <Button
            size="icon"
            variant="ghost"
            onClick={() => {
              setDraft(q);
              setOpen(true);
            }}
            aria-label="Edit"
          >
            <Edit className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="text-danger hover:bg-danger/10"
            onClick={onRemove}
            aria-label="Delete"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent description="Tweak the question text, expected answer, marks, and keywords before saving.">
          <DialogHeader>
            <DialogTitle>Edit question {index + 1}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Question</Label>
              <Textarea
                value={draft.question}
                onChange={(e) =>
                  setDraft({ ...draft, question: e.target.value })
                }
                rows={3}
              />
            </div>
            <div>
              <Label>Expected answer</Label>
              <Textarea
                value={draft.expected_answer || ""}
                onChange={(e) =>
                  setDraft({ ...draft, expected_answer: e.target.value })
                }
                rows={2}
              />
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <div>
                <Label>Marks</Label>
                <Input
                  type="number"
                  min={1}
                  max={100}
                  value={draft.marks ?? 5}
                  onChange={(e) =>
                    setDraft({ ...draft, marks: Number(e.target.value) || 1 })
                  }
                />
              </div>
              <div>
                <Label>Keywords</Label>
                <Input
                  value={(draft.keywords || []).join(", ")}
                  onChange={(e) =>
                    setDraft({
                      ...draft,
                      keywords: e.target.value
                        .split(",")
                        .map((k) => k.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">Cancel</Button>
            </DialogClose>
            <Button
              onClick={() => {
                onEdit(draft);
                setOpen(false);
              }}
            >
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
