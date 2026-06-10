"use client";

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { MessageCircle, Send } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/client-api";
import { formatRelative, cn } from "@/lib/utils";

export const CHAT_CONTACTS_KEY = ["chat-contacts"] as const;
const CHAT_THREAD_KEY = (id: string) => ["chat-thread", id] as const;

export function ChatBell() {
  const [open, setOpen] = React.useState(false);
  const qc = useQueryClient();
  // `null` = let the first contact be auto-selected. The user can override.
  const [picked, setPicked] = React.useState<string | null>(null);
  const [draft, setDraft] = React.useState("");

  const { data: contactsData } = useQuery({
    queryKey: CHAT_CONTACTS_KEY,
    queryFn: api.chatContacts,
    refetchInterval: 15_000,
  });
  const contacts = React.useMemo(
    () => contactsData?.contacts ?? [],
    [contactsData]
  );
  const totalUnread = contacts.reduce((sum, c) => sum + (c.unread || 0), 0);

  // Effective selection: user pick wins, otherwise auto-pick the first
  // contact when the dialog is open. Derived from current state — no
  // setState-in-effect cascade.
  const selected =
    picked ?? (open && contacts.length > 0 ? contacts[0].user_id : null);
  const activeContact = contacts.find((c) => c.user_id === selected);

  const { data: thread, isLoading } = useQuery({
    queryKey: selected ? CHAT_THREAD_KEY(selected) : ["chat-thread", "none"],
    queryFn: () => api.chatThread(selected!),
    enabled: !!selected && open,
    refetchInterval: open ? 15_000 : false,
  });

  // Mark thread read as soon as the user opens it.
  const markRead = useMutation({ mutationFn: api.chatMarkRead });
  React.useEffect(() => {
    if (open && selected) {
      markRead.mutate(selected, {
        onSuccess: () => {
          qc.invalidateQueries({ queryKey: CHAT_CONTACTS_KEY });
        },
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, selected]);

  const send = useMutation({
    mutationFn: ({ to, msg }: { to: string; msg: string }) =>
      api.chatSend(to, msg),
    onSuccess: () => {
      setDraft("");
      if (selected) {
        qc.invalidateQueries({ queryKey: CHAT_THREAD_KEY(selected) });
        qc.invalidateQueries({ queryKey: CHAT_CONTACTS_KEY });
      }
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  const onSend = () => {
    const text = draft.trim();
    if (!text || !selected) return;
    send.mutate({ to: selected, msg: text });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant={totalUnread > 0 ? "default" : "ghost"}
          size="sm"
          aria-label={`Messages (${totalUnread} unread)`}
          className="relative"
        >
          <MessageCircle className="h-4 w-4" />
          {totalUnread > 0 && (
            <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">
              {totalUnread > 99 ? "99+" : totalUnread}
            </span>
          )}
        </Button>
      </DialogTrigger>
      <DialogContent
        className="max-w-3xl"
        description="Direct messages with your teachers, students, or admin."
      >
        <DialogHeader>
          <DialogTitle>💬 Messages</DialogTitle>
        </DialogHeader>

        {contacts.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No one to chat with yet. Teachers can chat with students in their
            assigned classes; students can chat with their assigned teachers.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="space-y-1 md:col-span-1">
              <p className="text-xs text-muted-foreground">
                {contacts.length} contact{contacts.length === 1 ? "" : "s"}
              </p>
              {contacts.map((c) => (
                <button
                  key={c.user_id}
                  onClick={() => setPicked(c.user_id)}
                  className={cn(
                    "block w-full rounded-md px-3 py-2 text-left transition-colors",
                    c.user_id === selected
                      ? "bg-primary text-primary-foreground"
                      : "hover:bg-muted"
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">{c.name}</span>
                    {c.unread > 0 && (
                      <span className="rounded-full bg-danger px-1.5 text-[10px] font-bold text-white">
                        {c.unread}
                      </span>
                    )}
                  </div>
                  {c.last_message && (
                    <div className="mt-0.5 truncate text-xs opacity-80">
                      {c.last_message}
                    </div>
                  )}
                </button>
              ))}
            </div>

            <div className="flex flex-col md:col-span-2">
              {activeContact ? (
                <>
                  <div className="border-b border-border pb-2">
                    <div className="text-sm font-semibold">{activeContact.name}</div>
                    <div className="text-xs text-muted-foreground">
                      {activeContact.role}
                      {activeContact.class_section &&
                        ` · Class ${activeContact.class_section}`}
                    </div>
                  </div>
                  <div className="my-3 max-h-80 min-h-40 flex-1 overflow-y-auto space-y-2 pr-1">
                    {isLoading && (
                      <p className="text-center text-xs text-muted-foreground">
                        Loading…
                      </p>
                    )}
                    {!isLoading && (thread?.messages?.length ?? 0) === 0 && (
                      <p className="text-center text-xs text-muted-foreground">
                        Say hi to start the conversation.
                      </p>
                    )}
                    {(thread?.messages || []).map((m, i) => {
                      const fromMe = String(m.from_user_id) === String(thread?.me_id);
                      // Backend ought to send a stable `id`, but if anything
                      // ever returns null/duplicate ids the composite key
                      // keeps React's reconciler happy and noise out of the
                      // console.
                      const key = m.id || `${m.from_user_id}-${m.created_at}-${i}`;
                      return (
                        <div
                          key={key}
                          className={cn(
                            "flex",
                            fromMe ? "justify-end" : "justify-start"
                          )}
                        >
                          <div
                            className={cn(
                              "max-w-[75%] rounded-lg px-3 py-1.5 text-sm",
                              fromMe
                                ? "bg-primary text-primary-foreground"
                                : "bg-surface-3 text-foreground"
                            )}
                          >
                            <div className="whitespace-pre-wrap">
                              {m.message}
                            </div>
                            <div className="mt-0.5 text-[10px] opacity-70">
                              {formatRelative(m.created_at)}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <div className="flex items-end gap-2">
                    <Textarea
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      placeholder="Type your message…"
                      rows={2}
                      className="resize-none"
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                          e.preventDefault();
                          onSend();
                        }
                      }}
                    />
                    <Button
                      onClick={onSend}
                      disabled={!draft.trim() || send.isPending}
                      size="icon"
                    >
                      <Send className="h-4 w-4" />
                    </Button>
                  </div>
                </>
              ) : (
                <p className="text-center text-sm text-muted-foreground">
                  Pick a contact to start chatting.
                </p>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
