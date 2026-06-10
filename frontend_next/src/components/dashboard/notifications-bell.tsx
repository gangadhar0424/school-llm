"use client";

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { api, ApiError } from "@/lib/client-api";
import { formatRelative, cn } from "@/lib/utils";
import { useRealtime } from "@/lib/use-realtime";
import type { NotificationItem } from "@/lib/types";

const TYPE_ICON: Record<string, string> = {
  assignment_published: "📋",
  submission_received: "📥",
  deadline_today: "⏰",
  new_message: "💬",
};

export const NOTIF_COUNT_KEY = ["notifications-unread-count"] as const;
export const NOTIF_LIST_KEY = ["notifications"] as const;

export function NotificationsBell() {
  const [open, setOpen] = React.useState(false);
  const qc = useQueryClient();

  // When the WebSocket is up the server pushes notification.created /
  // notification.read events and React Query refetches instantly. We
  // drop the polling cadence to a slow safety-net (60s). If the WS
  // ever drops we automatically fall back to 30s polling.
  const realtime = useRealtime();
  const wsUp = realtime === "open";

  const { data: countData } = useQuery({
    queryKey: NOTIF_COUNT_KEY,
    queryFn: api.unreadCount,
    refetchInterval: wsUp ? 60_000 : 30_000,
    refetchIntervalInBackground: false,
  });
  const count = countData?.unread_count ?? 0;

  const { data: list, isLoading } = useQuery({
    queryKey: NOTIF_LIST_KEY,
    queryFn: api.notifications,
    enabled: open,
    refetchInterval: open ? (wsUp ? 60_000 : 15_000) : false,
    refetchIntervalInBackground: false,
  });

  const markRead = useMutation({
    mutationFn: api.markNotificationRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: NOTIF_COUNT_KEY });
      qc.invalidateQueries({ queryKey: NOTIF_LIST_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });
  const markAll = useMutation({
    mutationFn: api.markAllNotificationsRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: NOTIF_COUNT_KEY });
      qc.invalidateQueries({ queryKey: NOTIF_LIST_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  const notifs = list?.notifications ?? [];
  const unreadPersisted = notifs.filter(
    (n) => !n.is_read && !n._synthetic
  );

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant={count > 0 ? "default" : "ghost"}
          size="sm"
          aria-label={`Notifications (${count} unread)`}
          className="relative"
        >
          <Bell className="h-4 w-4" />
          {count > 0 && (
            <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-bold text-white">
              {count > 99 ? "99+" : count}
            </span>
          )}
        </Button>
      </DialogTrigger>
      <DialogContent
        className="max-w-2xl"
        description="Recent activity from teachers, deadlines, and messages."
      >
        <DialogHeader>
          <DialogTitle>🔔 Notifications</DialogTitle>
        </DialogHeader>

        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            {notifs.length} notification{notifs.length === 1 ? "" : "s"}
          </p>
          {unreadPersisted.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => markAll.mutate()}
              disabled={markAll.isPending}
            >
              Mark all read
            </Button>
          )}
        </div>

        <Separator />

        <div className="max-h-[60vh] space-y-2 overflow-y-auto">
          {isLoading && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              Loading…
            </p>
          )}
          {!isLoading && notifs.length === 0 && (
            <p className="py-6 text-center text-sm text-muted-foreground">
              You&apos;re all caught up. No notifications yet.
            </p>
          )}
          {notifs.map((n) => (
            <NotifRow key={getId(n)} n={n} onMarkRead={(id) => markRead.mutate(id)} />
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function getId(n: NotificationItem): string {
  return (n.id || n._id || `synth_${n.created_at}_${n.type}`) as string;
}

function NotifRow({
  n,
  onMarkRead,
}: {
  n: NotificationItem;
  onMarkRead: (id: string) => void;
}) {
  const synthetic = !!n._synthetic;
  const icon = TYPE_ICON[n.type] || "🔔";
  const id = getId(n);
  return (
    <div
      className={cn(
        "rounded-lg border p-3",
        n.is_read
          ? "border-border bg-surface-2"
          : "border-primary/40 bg-primary-chip"
      )}
    >
      <div className="flex items-start gap-3">
        <span className="text-lg">{icon}</span>
        <div className="flex-1">
          <div
            className={cn(
              "text-sm font-medium",
              n.is_read ? "text-muted-foreground" : "text-foreground"
            )}
          >
            {n.title}
          </div>
          {n.body && (
            <div className="mt-0.5 text-xs text-muted-foreground">{n.body}</div>
          )}
          <div className="mt-1 text-[10px] text-muted-foreground">
            {formatRelative(n.created_at)}
            {synthetic && " · auto-detected"}
          </div>
        </div>
        {!n.is_read && !synthetic && (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs"
            onClick={() => onMarkRead(id)}
          >
            Mark read
          </Button>
        )}
      </div>
    </div>
  );
}
