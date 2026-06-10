"use client";

import * as React from "react";
import { School } from "lucide-react";
import { NotificationsBell } from "./notifications-bell";
import { ChatBell } from "./chat-bell";

/**
 * Standard page header used on every dashboard page.
 *
 * Layout:
 *   ┌──────────────────────────────────────────────────────────┐
 *   │ Title              [school chip] [actions] 🔔  💬       │
 *   │ Subtitle / one-line description                           │
 *   └──────────────────────────────────────────────────────────┘
 *
 * - `title`     — required. Short, no emoji on admin (style guide).
 * - `subtitle`  — optional one-line description. Renders muted under
 *                 the title at smaller weight.
 * - `schoolChip`— optional read-only chip that anchors context across
 *                 admin pages (e.g. "Default School"). The admin sees
 *                 the same chip wherever they navigate so they never
 *                 lose track of which tenant they're looking at.
 * - `actions`   — optional page-level action buttons (Refresh, +Invite,
 *                 etc). Sit immediately before the notification/chat
 *                 bells so the bells stay anchored on the far right
 *                 across every page.
 * - `children`  — legacy slot, treated the same as `actions`. Kept for
 *                 the small number of pages that already use it.
 */
export function DashboardHeader({
  title,
  subtitle,
  schoolChip,
  actions,
  children,
}: {
  title: string;
  subtitle?: string;
  schoolChip?: string | null;
  actions?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <header className="flex flex-col gap-3 border-b border-border bg-surface px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-4 sm:px-6">
      <div className="min-w-0 ml-12 sm:ml-0">
        <h1 className="truncate text-xl font-semibold tracking-tight text-foreground">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p>
        )}
      </div>
      <div className="flex items-center gap-2">
        {schoolChip && (
          <span
            className="hidden items-center gap-1.5 rounded-md border border-border bg-muted px-2 py-1 text-xs text-muted-foreground md:inline-flex"
            title="Current school"
          >
            <School className="h-3 w-3" />
            <span className="max-w-48 truncate">{schoolChip}</span>
          </span>
        )}
        {actions}
        {children}
        <NotificationsBell />
        <ChatBell />
      </div>
    </header>
  );
}
