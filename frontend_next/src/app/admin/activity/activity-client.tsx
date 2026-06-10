"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Search } from "lucide-react";
import { api } from "@/lib/client-api";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DataTable,
  type DataTableColumn,
} from "@/components/ui/data-table";
import { PersonSheet } from "@/components/admin/person-sheet";
import { ExportButton } from "@/components/admin/export-button";
import { csvDate, type ExportColumn } from "@/lib/csv-export";
import { useCurrentUser } from "@/lib/use-current-user";
import { formatRelative } from "@/lib/utils";
import type { ActivityLog } from "@/lib/types";

/** A row in the activity table. Either a raw ActivityLog as the backend
 *  sends it, or a collapsed login group that carries the most recent
 *  login plus a `login_count` of how many logins it represents. */
type ActivityRow = ActivityLog & { login_count?: number };

const ACTION_FILTERS = [
  "all",
  "login",
  "logout",
  "signup",
  "qa",
  "quiz",
  "summary",
  "audio",
  "video",
  "pdf_upload",
] as const;
type ActionFilter = (typeof ACTION_FILTERS)[number];

export function AdminActivityClient() {
  const user = useCurrentUser();
  const [email, setEmail] = React.useState("");
  const [debouncedEmail, setDebouncedEmail] = React.useState("");
  const [action, setAction] = React.useState<ActionFilter>("all");
  // Phase 7.3 — the user_email column doubles as the entry point to the
  // canonical PersonSheet. Click an email → look it up → offer a deep
  // link to /admin/teachers/<id> or /admin/students/<id>.
  const [personEmail, setPersonEmail] = React.useState<string | null>(null);

  React.useEffect(() => {
    const t = setTimeout(() => setDebouncedEmail(email.trim()), 350);
    return () => clearTimeout(t);
  }, [email]);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-activity", debouncedEmail],
    queryFn: () =>
      api.adminGetActivity({
        limit: 500,
        user_email: debouncedEmail || undefined,
      }),
  });

  const rows = React.useMemo(() => {
    const all = data?.activities ?? [];
    const filtered =
      action === "all" ? all : all.filter((r) => r.activity_type === action);

    // Collapse repeat logins per user. The audit feed is noisy with
    // login spam — keep one row per user (the most recent login) and
    // attach a count so the admin can still see "this user logged in 6
    // times today" without scrolling. Other activity types pass through
    // untouched because each one is a distinct meaningful event.
    const lastLoginByUser = new Map<string, ActivityRow>();
    const loginCountByUser = new Map<string, number>();
    const out: ActivityRow[] = [];
    for (const r of filtered) {
      if (r.activity_type !== "login") {
        out.push(r);
        continue;
      }
      const seen = lastLoginByUser.get(r.user_email);
      loginCountByUser.set(
        r.user_email,
        (loginCountByUser.get(r.user_email) ?? 0) + 1
      );
      if (!seen || new Date(r.timestamp) > new Date(seen.timestamp)) {
        lastLoginByUser.set(r.user_email, r);
      }
    }
    for (const [email, last] of lastLoginByUser) {
      out.push({ ...last, login_count: loginCountByUser.get(email) ?? 1 });
    }
    // Sort the merged set by timestamp descending so the layout matches
    // what the admin saw before — newest at the top.
    out.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
    return out;
  }, [data, action]);

  // Activity logs don't carry a primary key from the backend, so we synth
  // a composite one. Index-suffixed in case two rows have the same
  // timestamp+user+action.
  const keyCounterRef = React.useRef(0);
  const rowKey = React.useCallback((r: ActivityRow): string => {
    keyCounterRef.current += 1;
    return `${r.timestamp}-${r.user_email}-${r.activity_type}-${keyCounterRef.current}`;
  }, []);
  // Reset the counter whenever the rows reference changes so keys stay
  // stable within a render of the same array.
  React.useEffect(() => {
    keyCounterRef.current = 0;
  }, [rows]);

  const columns: DataTableColumn<ActivityRow>[] = [
    {
      key: "user",
      header: "User",
      sortable: true,
      sortValue: (r) => r.user_email,
      cell: (r) => (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setPersonEmail(r.user_email);
          }}
          className="truncate text-left text-sm font-medium text-foreground hover:text-primary hover:underline"
        >
          {r.user_email}
        </button>
      ),
    },
    {
      key: "activity_type",
      header: "Action",
      sortable: true,
      sortValue: (r) => r.activity_type,
      width: "w-32",
      cell: (r) => (
        <Badge variant="outline" className="font-normal">
          {r.activity_type}
          {r.login_count && r.login_count > 1 && (
            <span className="ml-1 text-muted-foreground">
              ({r.login_count})
            </span>
          )}
        </Badge>
      ),
    },
    {
      key: "details",
      header: "Details",
      cell: (r) =>
        r.details ? (
          <span className="line-clamp-1 text-xs text-muted-foreground">
            {typeof r.details === "string"
              ? r.details
              : JSON.stringify(r.details)}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        ),
    },
    {
      key: "timestamp",
      header: "When",
      sortable: true,
      sortValue: (r) => new Date(r.timestamp).getTime(),
      width: "w-40",
      align: "right",
      cell: (r) => (
        <div className="text-xs text-muted-foreground">
          {r.login_count && r.login_count > 1 && (
            <div className="text-[10px] uppercase tracking-wide">
              last login
            </div>
          )}
          {formatRelative(r.timestamp)}
        </div>
      ),
    },
  ];

  const exportColumns: ExportColumn<ActivityRow>[] = React.useMemo(
    () => [
      { header: "User", value: (r) => r.user_email ?? "" },
      { header: "Action", value: (r) => r.activity_type ?? "" },
      {
        header: "Login count",
        value: (r) => (r.login_count && r.login_count > 1 ? r.login_count : ""),
      },
      {
        header: "Details",
        value: (r) =>
          r.details
            ? typeof r.details === "string"
              ? r.details
              : JSON.stringify(r.details)
            : "",
      },
      { header: "When", value: (r) => csvDate(r.timestamp) },
    ],
    []
  );
  const activeFilters = React.useMemo(() => {
    const bits: string[] = [];
    if (debouncedEmail) bits.push(`user_email=${debouncedEmail}`);
    if (action !== "all") bits.push(`action=${action}`);
    return bits.length === 0 ? "none" : bits.join(", ");
  }, [debouncedEmail, action]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Filter by user email…"
            className="h-9 pl-8"
          />
        </div>
        <Select
          value={action}
          onValueChange={(v) => setAction(v as ActionFilter)}
        >
          <SelectTrigger className="h-9 sm:w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ACTION_FILTERS.map((a) => (
              <SelectItem key={a} value={a} className="capitalize">
                {a === "all" ? "All actions" : a.replace("_", " ")}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <ExportButton
          label="Export"
          loading={isLoading}
          disabled={rows.length === 0}
          options={() => ({
            subject: "Activity log",
            schoolName: user?.school_name ?? null,
            filters: activeFilters,
            columns: exportColumns,
            rows: rows,
          })}
        />
      </div>

      <DataTable<ActivityRow>
        data={rows}
        columns={columns}
        rowKey={rowKey}
        loading={isLoading}
        pageSize={50}
        empty={
          <div className="flex flex-col items-center gap-2 py-6">
            <Activity className="h-6 w-6 text-muted-foreground" />
            <p className="text-sm font-medium">No activity</p>
            <p className="text-xs text-muted-foreground">
              {debouncedEmail || action !== "all"
                ? "Try clearing the filters."
                : "Wait for a user to do something."}
            </p>
          </div>
        }
      />

      <PersonSheet
        email={personEmail}
        open={!!personEmail}
        onOpenChange={(open) => !open && setPersonEmail(null)}
      />
    </div>
  );
}
