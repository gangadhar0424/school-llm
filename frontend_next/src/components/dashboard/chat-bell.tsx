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
import { useRealtime } from "@/lib/use-realtime";
import { useCurrentUser } from "@/lib/use-current-user";

export const CHAT_CONTACTS_KEY = ["chat-contacts"] as const;
const CHAT_THREAD_KEY = (id: string) => ["chat-thread", id] as const;

export function ChatBell() {
  const [open, setOpen] = React.useState(false);
  const qc = useQueryClient();
  const [picked, setPicked] = React.useState<string | null>(null);
  const [draft, setDraft] = React.useState("");

  const realtime = useRealtime();
  const wsUp = realtime === "open";

  const user = useCurrentUser();
  const isSuperAdmin = user?.role === "super_admin";

  const { data: contactsData } = useQuery({
    queryKey: CHAT_CONTACTS_KEY,
    queryFn: api.chatContacts,
    refetchInterval: wsUp ? 60_000 : 30_000,
    refetchIntervalInBackground: false,
    enabled: !isSuperAdmin,
  });
  const contacts = React.useMemo(
    () => contactsData?.contacts ?? [],
    [contactsData]
  );
  const totalUnread = contacts.reduce((sum, c) => sum + (c.unread || 0), 0);

  const [isSearching, setIsSearching] = React.useState(false);
  const [searchQuery, setSearchQuery] = React.useState("");

  // Super Admin Specific State
  const { data: schoolsData } = useQuery({
    queryKey: ["super-admin-schools"],
    queryFn: api.superAdminSchools,
    enabled: isSuperAdmin,
  });
  const [pickedSchool, setPickedSchool] = React.useState<number | null>(null);
  const [saTarget, setSaTarget] = React.useState<"all" | "admin">("all");

  const activeContacts = React.useMemo(() => {
    return contacts.filter(
      (c) => c.role === "group" || c.last_message || c.user_id === picked
    );
  }, [contacts, picked]);

  const selected = picked ?? (open && activeContacts.length > 0 ? activeContacts[0].user_id : null);
  const activeContact = contacts.find((c) => c.user_id === selected);

  const { data: thread, isLoading } = useQuery({
    queryKey: selected ? CHAT_THREAD_KEY(selected) : ["chat-thread", "none"],
    queryFn: () => api.chatThread(selected!),
    enabled: !!selected && open && !isSuperAdmin,
    refetchInterval: open ? (wsUp ? 60_000 : 15_000) : false,
    refetchIntervalInBackground: false,
  });

  const markRead = useMutation({ mutationFn: api.chatMarkRead });
  React.useEffect(() => {
    if (open && selected && !isSuperAdmin) {
      markRead.mutate(selected, {
        onSuccess: () => {
          qc.invalidateQueries({ queryKey: CHAT_CONTACTS_KEY });
        },
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, selected, isSuperAdmin]);

  const send = useMutation({
    mutationFn: ({ to, msg }: { to: string; msg: string }) =>
      api.chatSend(to, msg),
    onSuccess: () => {
      setDraft("");
      if (selected && !isSuperAdmin) {
        qc.invalidateQueries({ queryKey: CHAT_THREAD_KEY(selected) });
        qc.invalidateQueries({ queryKey: CHAT_CONTACTS_KEY });
      } else if (isSuperAdmin) {
        toast.success("Broadcast message sent successfully!");
      }
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  const onSend = () => {
    const text = draft.trim();
    if (!text) return;
    if (isSuperAdmin && pickedSchool !== null) {
      send.mutate({ to: `broadcast_school_${saTarget}_${pickedSchool}`, msg: text });
      return;
    }
    if (!selected) return;
    send.mutate({ to: selected, msg: text });
  };

  const superAdminSchools = (schoolsData?.schools || []).filter(s => 
    s.name.toLowerCase().includes(searchQuery.toLowerCase())
  );
  
  const selectedSchoolObj = schoolsData?.schools.find(s => s.school_id === pickedSchool);
  
  // Set default selected school for super admin if none selected
  React.useEffect(() => {
    if (isSuperAdmin && open && !pickedSchool && superAdminSchools.length > 0) {
        setPickedSchool(superAdminSchools[0].school_id);
    }
  }, [isSuperAdmin, open, pickedSchool, superAdminSchools]);

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

        {isSuperAdmin ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="space-y-1 md:col-span-1 border-r pr-2 flex flex-col h-[400px]">
              <div className="flex items-center justify-between shrink-0 mb-2">
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Schools
                </p>
              </div>
              <input 
                placeholder="Search schools..."
                className="flex h-8 w-full shrink-0 mb-2 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />
              <div className="overflow-y-auto space-y-1 pb-2 flex-1">
                {superAdminSchools.length === 0 ? (
                  <p className="text-xs text-muted-foreground text-center mt-4">No schools found.</p>
                ) : (
                  superAdminSchools.map(s => {
                    const sid = s.school_id ?? -1;
                    return (
                      <button
                        key={sid}
                        onClick={() => setPickedSchool(sid)}
                        className={cn(
                          "block w-full rounded-md px-3 py-2 text-left transition-colors",
                          pickedSchool === sid
                            ? "bg-primary text-primary-foreground"
                            : "hover:bg-muted"
                        )}
                      >
                         <span className="text-sm font-medium">{s.name}</span>
                         <div className="text-[10px] opacity-70 mt-0.5">{s.user_count} users</div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>

            <div className="flex flex-col md:col-span-2">
              {selectedSchoolObj ? (
                <>
                  <div className="border-b border-border pb-2">
                    <div className="text-sm font-semibold">Message School: {selectedSchoolObj.name}</div>
                    <div className="text-xs text-muted-foreground">
                      Broadcast to {selectedSchoolObj.user_count} users
                    </div>
                  </div>
                  
                  <div className="my-3 flex-1 flex flex-col justify-end">
                    <p className="text-center text-xs text-muted-foreground mb-4">
                      Write your message below to send a broadcast to this school. 
                      Replies will not appear in this window.
                    </p>
                  </div>
                  
                  <div className="flex flex-col gap-2">
                    <div className="flex items-center gap-2 mb-1">
                      <label className="text-xs font-medium text-muted-foreground">Send to:</label>
                      <select 
                        className="text-xs border rounded-md p-1 bg-surface focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                        value={saTarget}
                        onChange={(e) => setSaTarget(e.target.value as "all" | "admin")}
                      >
                        <option value="all">Everyone in the school</option>
                        <option value="admin">Admin only</option>
                      </select>
                    </div>
                    <div className="flex items-end gap-2">
                      <Textarea
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        placeholder="Type your broadcast message…"
                        rows={3}
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
                  </div>
                </>
              ) : (
                <p className="text-center text-sm text-muted-foreground mt-10">
                  Pick a school from the left to send a broadcast message.
                </p>
              )}
            </div>
          </div>
        ) : contacts.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            No one to chat with yet. Teachers can chat with students in their
            assigned classes; students can chat with their assigned teachers.
          </p>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="space-y-1 md:col-span-1 border-r pr-2 flex flex-col h-[400px]">
              <div className="flex items-center justify-between shrink-0 mb-1">
                <p className="text-xs text-muted-foreground">
                  {isSearching ? "Search Contacts" : `${activeContacts.length} active`}
                </p>
                {isSearching && (
                  <button onClick={() => { setIsSearching(false); setSearchQuery(""); }} className="text-xs text-muted-foreground hover:text-foreground">
                    Cancel
                  </button>
                )}
              </div>
              
              {isSearching ? (
                <div className="flex flex-col overflow-hidden">
                  <input 
                    autoFocus
                    placeholder="Search by name..."
                    className="flex h-8 w-full shrink-0 mb-2 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                  />
                  <div className="overflow-y-auto space-y-1 pb-2">
                    {contacts.filter(c => c.role !== "group" && c.name.toLowerCase().includes(searchQuery.toLowerCase())).map(c => (
                      <button
                        key={c.user_id}
                        onClick={() => { setPicked(c.user_id); setIsSearching(false); setSearchQuery(""); }}
                        className={cn(
                          "block w-full rounded-md px-3 py-2 text-left transition-colors",
                          c.user_id === selected
                            ? "bg-primary text-primary-foreground"
                            : "hover:bg-muted"
                        )}
                      >
                          <span className="text-sm font-medium">{c.name}</span>
                          <div className="text-[10px] opacity-70 mt-0.5">{c.role} {c.class_section ? `· ${c.class_section}` : ''}</div>
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="flex flex-col overflow-hidden">
                  <div className="overflow-y-auto space-y-1 pb-2">
                    {activeContacts.map((c) => (
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
                  <Button variant="outline" size="sm" className="w-full shrink-0 justify-center text-xs mt-2" onClick={() => setIsSearching(true)}>
                    + Message Individual
                  </Button>
                </div>
              )}
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
                <p className="text-center text-sm text-muted-foreground mt-10">
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
