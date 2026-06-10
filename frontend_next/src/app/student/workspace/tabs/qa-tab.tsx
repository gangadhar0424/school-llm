"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Send, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { cn, formatRelative } from "@/lib/utils";
import { USAGE_QUERY_KEY } from "@/components/dashboard/usage-card";
import { useFakeStream } from "../use-fake-stream";
import type { ChatSessionSummary } from "@/lib/types";

const SESSIONS_KEY = (mode: "single" | "multi") =>
  ["chat-sessions", mode] as const;
const SESSION_KEY = (id: string) => ["chat-session", id] as const;

export function QATab({
  pdfId,
  pdfName,
}: {
  pdfId: string;
  pdfName: string;
}) {
  return (
    <ChatPanel
      mode="single"
      pdfIds={[pdfId]}
      header={
        <>
          💬 <strong>Q&amp;A</strong> grounded on{" "}
          <span className="text-foreground">{pdfName || "(select a PDF)"}</span>
        </>
      }
      ask={(question, sessionId) =>
        api.ask({ pdf_url: pdfId, question, session_id: sessionId })
      }
    />
  );
}

export function ChatPanel({
  mode,
  pdfIds,
  header,
  ask,
}: {
  mode: "single" | "multi";
  pdfIds: string[];
  header: React.ReactNode;
  ask: (
    question: string,
    sessionId: string
  ) => Promise<{ answer: string; sources?: string[] }>;
}) {
  const qc = useQueryClient();
  const [activeId, setActiveId] = React.useState<string | null>(null);
  const [draft, setDraft] = React.useState("");

  const sessions = useQuery({
    queryKey: SESSIONS_KEY(mode),
    queryFn: () => api.listChatSessions(mode),
  });

  const createSession = useMutation({
    mutationFn: (name: string) =>
      api.createChatSession({
        pdf_ids: pdfIds,
        mode,
        name,
      }),
    onSuccess: (resp) => {
      qc.invalidateQueries({ queryKey: SESSIONS_KEY(mode) });
      setActiveId(resp.id);
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  const deleteSession = useMutation({
    mutationFn: (id: string) => api.deleteChatSession(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: SESSIONS_KEY(mode) });
      setActiveId(null);
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  const session = useQuery({
    queryKey: activeId ? SESSION_KEY(activeId) : ["chat-session", "none"],
    queryFn: () => api.getChatSession(activeId!),
    enabled: !!activeId,
  });

  const askM = useMutation({
    mutationFn: ({ q, sid }: { q: string; sid: string }) => ask(q, sid),
    onSuccess: () => {
      // Refresh the session so the persisted user+assistant pair lands.
      if (activeId) {
        qc.invalidateQueries({ queryKey: SESSION_KEY(activeId) });
      }
      qc.invalidateQueries({ queryKey: USAGE_QUERY_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  const sendQuestion = () => {
    const q = draft.trim();
    if (!q) return;
    if (!activeId) {
      // Auto-create a session, then send once it lands.
      createSession.mutate("New chat", {
        onSuccess: (resp) => {
          setDraft("");
          askM.mutate({ q, sid: resp.id });
        },
      });
      return;
    }
    setDraft("");
    askM.mutate({ q, sid: activeId });
  };

  // Derive the optimistic-UI state from the mutation + query rather than
  // tracking it as separate state with effect resets (React 19 forbids
  // setState in effect bodies).
  const pendingQuestion: string | null =
    askM.isPending || (askM.data && !sessionContainsAnswer(session.data, askM.data.answer))
      ? (askM.variables?.q ?? null)
      : null;
  const pendingAnswer: string | null = askM.data?.answer ?? null;
  const pendingSources: string[] = askM.data?.sources ?? [];

  const sessionList = sessions.data?.sessions ?? [];

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[260px_1fr]">
      {/* Sessions */}
      <Card className="md:max-h-[70vh]">
        <CardContent className="flex h-full flex-col gap-2 p-3">
          <Button
            size="sm"
            onClick={() => createSession.mutate("New chat")}
            disabled={createSession.isPending}
          >
            <Plus className="h-4 w-4" />
            New chat
          </Button>
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Recent
          </div>
          <div className="flex-1 space-y-1 overflow-y-auto">
            {sessions.isLoading && <Skeleton className="h-8 w-full" />}
            {sessionList.length === 0 && !sessions.isLoading && (
              <p className="text-xs text-muted-foreground">
                No conversations yet.
              </p>
            )}
            {sessionList.map((s) => (
              <SessionRow
                key={s.id}
                s={s}
                active={activeId === s.id}
                onPick={() => setActiveId(s.id)}
                onDelete={() => deleteSession.mutate(s.id)}
              />
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Thread */}
      <Card className="flex flex-col md:max-h-[70vh]">
        <CardContent className="flex flex-1 flex-col gap-3 p-4">
          <div className="text-xs text-muted-foreground">{header}</div>

          <div className="flex-1 space-y-3 overflow-y-auto pr-1">
            {!activeId && (
              <p className="py-12 text-center text-sm text-muted-foreground">
                Start a chat to ask questions about your PDF.
              </p>
            )}
            {session.data?.messages.map((m, i) => (
              <Message
                key={i}
                role={m.role}
                content={m.content}
                sources={m.sources}
              />
            ))}
            {pendingQuestion && (
              <Message role="user" content={pendingQuestion} />
            )}
            {pendingQuestion && !pendingAnswer && (
              <Message role="assistant" content="💭 Thinking…" loading />
            )}
            {pendingAnswer && (
              <Message
                role="assistant"
                content={pendingAnswer}
                sources={pendingSources}
                animateStream
              />
            )}
          </div>

          {/* Input */}
          <div className="flex items-end gap-2 border-t border-border pt-3">
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask anything about the PDF…"
              rows={2}
              className="resize-none"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  sendQuestion();
                }
              }}
              disabled={askM.isPending}
            />
            <Button
              onClick={sendQuestion}
              disabled={
                !draft.trim() || askM.isPending || createSession.isPending
              }
              size="icon"
            >
              {askM.isPending || createSession.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
          <p className="text-[10px] text-muted-foreground">
            Press Enter to send · Shift+Enter for a new line
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function SessionRow({
  s,
  active,
  onPick,
  onDelete,
}: {
  s: ChatSessionSummary;
  active: boolean;
  onPick: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-1 rounded-md text-xs transition-colors",
        active ? "bg-primary/15" : "hover:bg-muted"
      )}
    >
      <button
        onClick={onPick}
        className="flex-1 truncate px-2 py-1.5 text-left"
        title={s.name}
      >
        {active ? "➤ " : ""}
        {s.name || "Untitled"}
        <div className="text-[10px] text-muted-foreground">
          {formatRelative(s.updated_at)} · {s.message_count} msg
        </div>
      </button>
      <button
        onClick={(e) => {
          e.stopPropagation();
          if (confirm("Delete this conversation?")) onDelete();
        }}
        className="rounded p-1 text-muted-foreground hover:text-danger"
        aria-label="Delete"
      >
        <Trash2 className="h-3 w-3" />
      </button>
    </div>
  );
}

function Message({
  role,
  content,
  sources,
  loading,
  animateStream,
}: {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  loading?: boolean;
  animateStream?: boolean;
}) {
  const stream = useFakeStream(animateStream ? content : null);
  const shown = animateStream ? stream.text : content;
  return (
    <div className={cn("flex", role === "user" ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-lg px-3 py-2 text-sm",
          role === "user"
            ? "bg-primary text-primary-foreground"
            : "bg-surface-3 text-foreground"
        )}
      >
        <div className="whitespace-pre-wrap">
          {loading ? <span className="opacity-75">{content}</span> : shown}
          {animateStream && !stream.done && (
            <span className="ml-0.5 inline-block h-3 w-2 animate-pulse bg-current align-middle" />
          )}
        </div>
        {sources && sources.length > 0 && (
          <div className="mt-1.5 border-t border-border/40 pt-1.5">
            <div className="text-[10px] font-semibold uppercase tracking-wide opacity-70">
              Sources
            </div>
            <ul className="ml-3 list-disc text-[11px] opacity-80">
              {sources.slice(0, 3).map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function sessionContainsAnswer(
  data: { messages: { role: string; content: string }[] } | undefined,
  answer: string | null
): boolean {
  if (!data || !answer) return false;
  return data.messages.some(
    (m) => m.role === "assistant" && m.content === answer
  );
}

// Re-export so multi-doc can build on top of this.
export { useFakeStream } from "../use-fake-stream";
