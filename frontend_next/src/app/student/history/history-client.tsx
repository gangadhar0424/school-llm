"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { MessageSquare, ClipboardList, FileText, Volume2, Video } from "lucide-react";
import { api } from "@/lib/client-api";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui/tabs";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { formatRelative } from "@/lib/utils";

export function HistoryClient() {
  return (
    <Tabs defaultValue="qa">
      <TabsList className="grid grid-cols-3 sm:grid-cols-5">
        <TabsTrigger value="qa" className="gap-1.5">
          <MessageSquare className="h-3.5 w-3.5" /> Q&amp;A
        </TabsTrigger>
        <TabsTrigger value="quiz" className="gap-1.5">
          <ClipboardList className="h-3.5 w-3.5" /> Quiz
        </TabsTrigger>
        <TabsTrigger value="summary" className="gap-1.5">
          <FileText className="h-3.5 w-3.5" /> Summary
        </TabsTrigger>
        <TabsTrigger value="audio" className="gap-1.5">
          <Volume2 className="h-3.5 w-3.5" /> Audio
        </TabsTrigger>
        <TabsTrigger value="video" className="gap-1.5">
          <Video className="h-3.5 w-3.5" /> Video
        </TabsTrigger>
      </TabsList>

      <TabsContent value="qa" className="pt-4">
        <QAHistory />
      </TabsContent>
      <TabsContent value="quiz" className="pt-4">
        <QuizHistory />
      </TabsContent>
      <TabsContent value="summary" className="pt-4">
        <SummaryHistory />
      </TabsContent>
      <TabsContent value="audio" className="pt-4">
        <AudioHistory />
      </TabsContent>
      <TabsContent value="video" className="pt-4">
        <VideoHistory />
      </TabsContent>
    </Tabs>
  );
}

function Empty({ label }: { label: string }) {
  return (
    <Card>
      <CardContent className="py-10 text-center text-sm text-muted-foreground">
        No {label} yet.
      </CardContent>
    </Card>
  );
}

function HistoryShell({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-2">{children}</div>;
}

function QAHistory() {
  const { data, isLoading } = useQuery({
    queryKey: ["history-qa"],
    queryFn: () => api.historyQA(50),
  });
  if (isLoading) return <Skeleton className="h-32 w-full" />;
  const items = data?.items ?? [];
  if (items.length === 0) return <Empty label="Q&A sessions" />;
  return (
    <HistoryShell>
      {items.map((s) => (
        <Card key={s.id}>
          <CardContent className="flex items-center justify-between p-4">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{s.name}</p>
              <p className="text-xs text-muted-foreground">
                {s.mode === "multi" ? "🔀 Multi-doc" : "💬 Single doc"} ·{" "}
                {s.message_count} message{s.message_count === 1 ? "" : "s"} ·{" "}
                {formatRelative(s.updated_at)}
              </p>
            </div>
            <Badge variant="outline">{s.message_count}</Badge>
          </CardContent>
        </Card>
      ))}
    </HistoryShell>
  );
}

function QuizHistory() {
  const { data, isLoading } = useQuery({
    queryKey: ["history-quizzes"],
    queryFn: () => api.historyQuizzes(50),
  });
  if (isLoading) return <Skeleton className="h-32 w-full" />;
  const items = data?.items ?? [];
  if (items.length === 0) return <Empty label="quiz attempts" />;
  return (
    <HistoryShell>
      {items.map((q) => {
        const tone =
          q.percent >= 80
            ? "success"
            : q.percent >= 50
              ? "warning"
              : "danger";
        return (
          <Card key={q.id}>
            <CardContent className="flex items-center justify-between p-4">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">
                  {q.question_type} · {q.difficulty}
                </p>
                <p className="text-xs text-muted-foreground">
                  PDF: {q.pdf_ref || "(deleted)"} · {formatRelative(q.submitted_at)}
                </p>
              </div>
              <Badge variant={tone}>
                {q.score}/{q.total} · {q.percent}%
              </Badge>
            </CardContent>
          </Card>
        );
      })}
    </HistoryShell>
  );
}

function SummaryHistory() {
  const { data, isLoading } = useQuery({
    queryKey: ["history-summaries"],
    queryFn: () => api.historySummaries(50),
  });
  if (isLoading) return <Skeleton className="h-32 w-full" />;
  const items = data?.items ?? [];
  if (items.length === 0) return <Empty label="summaries" />;
  return (
    <HistoryShell>
      {items.map((s) => (
        <Card key={s.id}>
          <CardContent className="flex items-center justify-between p-4">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">📄 {s.summary_type} summary</p>
              <p className="text-xs text-muted-foreground">
                PDF: {s.pdf_ref || "(deleted)"} · {formatRelative(s.created_at)}
              </p>
            </div>
            <Badge variant="outline">{s.summary_type}</Badge>
          </CardContent>
        </Card>
      ))}
    </HistoryShell>
  );
}

function AudioHistory() {
  const { data, isLoading } = useQuery({
    queryKey: ["history-audio"],
    queryFn: () => api.historyAudio(50),
  });
  if (isLoading) return <Skeleton className="h-32 w-full" />;
  const items = data?.items ?? [];
  if (items.length === 0) return <Empty label="audio files" />;
  return (
    <HistoryShell>
      {items.map((a) => (
        <Card key={a.id}>
          <CardContent className="space-y-2 p-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">🔊 {a.filename}</p>
              <Badge variant="outline">
                {Math.round(a.duration_estimate)}s
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              {formatRelative(a.created_at)} · voice: {a.voice}
            </p>
            <audio controls className="w-full" src={`/api/backend/audio/${a.filename}`} />
          </CardContent>
        </Card>
      ))}
    </HistoryShell>
  );
}

function VideoHistory() {
  const { data, isLoading } = useQuery({
    queryKey: ["history-video"],
    queryFn: () => api.historyVideo(50),
  });
  if (isLoading) return <Skeleton className="h-32 w-full" />;
  const items = data?.items ?? [];
  if (items.length === 0) return <Empty label="videos" />;
  return (
    <HistoryShell>
      {items.map((v) => (
        <Card key={v.id}>
          <CardContent className="space-y-2 p-4">
            <div className="flex items-center justify-between">
              <p className="text-sm font-medium">🎬 {v.filename}</p>
              <Badge variant="outline">{v.style}</Badge>
            </div>
            <p className="text-xs text-muted-foreground">
              {formatRelative(v.created_at)} · {Math.round(v.duration)}s
            </p>
            <video
              controls
              className="w-full rounded-md"
              src={`/api/backend/video/${v.filename}`}
            />
          </CardContent>
        </Card>
      ))}
    </HistoryShell>
  );
}
