"use client";

import { NotificationsBell } from "./notifications-bell";
import { ChatBell } from "./chat-bell";

/**
 * Header bar shown at the top of every dashboard page. Houses the
 * notifications + chat bells (poll every 15s) and the page title.
 */
export function DashboardHeader({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
}) {
  return (
    <header className="flex flex-col gap-3 border-b border-border bg-surface px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-6">
      <div className="ml-12 sm:ml-0">
        <h1 className="text-lg font-semibold text-foreground">{title}</h1>
        {subtitle && (
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        )}
      </div>
      <div className="flex items-center gap-2">
        {children}
        <NotificationsBell />
        <ChatBell />
      </div>
    </header>
  );
}
