"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Edit3,
  Loader2,
  Search,
  ShieldCheck,
  UserX,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
  type RowAction,
} from "@/components/ui/data-table";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Label } from "@/components/ui/label";
import { formatRelative, cn } from "@/lib/utils";
import type { AdminUser, Role } from "@/lib/types";

const ROLES: (Role | "all")[] = ["all", "student", "teacher", "admin"];
const SUBJECTS = ["Math", "Science", "English", "Social", "Computer"];
const SECTIONS = ["A", "B", "C"];
const CLASSES = Array.from({ length: 10 }, (_, i) => i + 1);
const ALL_CS = CLASSES.flatMap((c) => SECTIONS.map((s) => `${c}${s}`));

const USERS_KEY = ["admin-users"] as const;

export function AdminUsersClient() {
  const [search, setSearch] = React.useState("");
  const [roleFilter, setRoleFilter] = React.useState<Role | "all">("all");
  const [editingId, setEditingId] = React.useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: USERS_KEY,
    queryFn: api.adminGetUsers,
  });

  const filtered = React.useMemo(() => {
    const all = data?.users ?? [];
    return all.filter((u) => {
      if (roleFilter !== "all" && u.role !== roleFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        if (
          !u.email.toLowerCase().includes(q) &&
          !u.username.toLowerCase().includes(q) &&
          !(u.full_name || "").toLowerCase().includes(q)
        )
          return false;
      }
      return true;
    });
  }, [data, search, roleFilter]);

  const editingUser = React.useMemo(
    () => filtered.find((u) => (u.id || u._id) === editingId) ?? null,
    [filtered, editingId]
  );

  const columns: DataTableColumn<AdminUser>[] = [
    {
      key: "user",
      header: "User",
      sortable: true,
      sortValue: (u) => (u.full_name || u.username || u.email).toLowerCase(),
      cell: (u) => <UserCell user={u} />,
    },
    {
      key: "role",
      header: "Role",
      sortable: true,
      sortValue: (u) => u.role,
      width: "w-24",
      cell: (u) => (
        <Badge
          variant={u.role === "admin" ? "default" : "outline"}
          className="capitalize"
        >
          {u.role}
        </Badge>
      ),
    },
    {
      key: "scope",
      header: "Scope",
      cell: (u) =>
        u.role === "student" ? (
          <span className="text-xs text-muted-foreground">
            Class {u.class_section || `${u.class_level ?? "—"}${u.section ?? ""}`}
          </span>
        ) : u.role === "teacher" ? (
          <span className="text-xs text-muted-foreground">
            {(u.subjects_taught || []).join(", ") || "—"}
            {u.assigned_classes?.length
              ? ` · ${u.assigned_classes.join(", ")}`
              : ""}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">Full access</span>
        ),
    },
    {
      key: "last_login",
      header: "Last login",
      sortable: true,
      sortValue: (u) => (u.last_login ? new Date(u.last_login).getTime() : 0),
      width: "w-32",
      cell: (u) => (
        <span className="text-xs text-muted-foreground">
          {u.last_login ? formatRelative(u.last_login) : "never"}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      sortable: true,
      sortValue: (u) => (u.is_active ? 1 : 0),
      width: "w-24",
      cell: (u) => (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 text-xs font-medium",
            u.is_active ? "text-success" : "text-muted-foreground"
          )}
        >
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              u.is_active ? "bg-success" : "bg-muted-foreground"
            )}
          />
          {u.is_active ? "Active" : "Inactive"}
        </span>
      ),
    },
  ];

  const rowActions = (u: AdminUser): RowAction[] => {
    const userId = (u.id || u._id) as string;
    const actions: RowAction[] = [
      {
        label: "Edit",
        icon: Edit3,
        onClick: () => setEditingId(userId),
      },
    ];
    if (u.is_active) {
      actions.push({
        label: "Deactivate",
        icon: UserX,
        destructive: true,
        onClick: () => toggleStatus(userId, false),
      });
    } else {
      actions.push({
        label: "Activate",
        icon: CheckCircle2,
        onClick: () => toggleStatus(userId, true),
      });
    }
    return actions;
  };

  const qc = useQueryClient();
  const toggleStatusM = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      api.adminUpdateUserStatus(id, active),
    onSuccess: (_d, vars) => {
      toast.success(vars.active ? "Activated" : "Deactivated");
      qc.invalidateQueries({ queryKey: USERS_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });
  const toggleStatus = (id: string, active: boolean) =>
    toggleStatusM.mutate({ id, active });

  return (
    <>
      <div className="space-y-4">
        {/* Filters */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name, username, or email…"
              className="h-9 pl-8"
            />
          </div>
          <Select
            value={roleFilter}
            onValueChange={(v) => setRoleFilter(v as Role | "all")}
          >
            <SelectTrigger className="h-9 sm:w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROLES.map((r) => (
                <SelectItem key={r} value={r} className="capitalize">
                  {r === "all" ? "All roles" : r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Table */}
        <DataTable<AdminUser>
          data={filtered}
          columns={columns}
          rowKey={(u) => (u.id || u._id) as string}
          loading={isLoading}
          empty={
            <div className="flex flex-col items-center gap-2 py-6">
              <ShieldCheck className="h-6 w-6 text-muted-foreground" />
              <p className="text-sm font-medium">No users match your filters</p>
              <p className="text-xs text-muted-foreground">
                Try clearing the search or switching roles.
              </p>
            </div>
          }
          rowActions={rowActions}
          pageSize={25}
        />
      </div>

      {/* Edit sheet */}
      <Sheet
        open={!!editingUser}
        onOpenChange={(open) => !open && setEditingId(null)}
      >
        <SheetContent description="Update this user's role-specific scope.">
          {editingUser ? (
            <>
              <SheetHeader>
                <SheetTitle>Edit user</SheetTitle>
                <p className="text-xs text-muted-foreground">
                  {editingUser.email}
                </p>
              </SheetHeader>
              <SheetBody>
                {editingUser.role === "student" && (
                  <StudentClassEditor user={editingUser} />
                )}
                {editingUser.role === "teacher" && (
                  <TeacherEditor user={editingUser} />
                )}
                {editingUser.role === "admin" && (
                  <p className="text-sm text-muted-foreground">
                    Admins have full system access — no per-class assignment
                    to edit. Use the status action in the row menu to revoke
                    access if needed.
                  </p>
                )}
              </SheetBody>
            </>
          ) : null}
        </SheetContent>
      </Sheet>
    </>
  );
}

// ── User cell (avatar + name + email) ────────────────────────────────────

function UserCell({ user }: { user: AdminUser }) {
  const initials = getInitials(user.full_name || user.username || user.email);
  return (
    <div className="flex items-center gap-2.5">
      <span
        aria-hidden
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary-chip text-[10px] font-semibold uppercase tracking-wide text-primary"
      >
        {initials}
      </span>
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-foreground">
          {user.full_name || user.username}
        </div>
        <div className="truncate text-xs text-muted-foreground">
          {user.email}
        </div>
      </div>
    </div>
  );
}

function getInitials(s: string): string {
  const parts = s.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// ── Student class editor (used in Sheet) ─────────────────────────────────

function StudentClassEditor({ user }: { user: AdminUser }) {
  const qc = useQueryClient();
  const userId = (user.id || user._id) as string;
  const [cls, setCls] = React.useState(String(user.class_level ?? 1));
  const [sec, setSec] = React.useState(user.section || "A");

  const save = useMutation({
    mutationFn: () => api.adminUpdateUserClass(userId, Number(cls), sec),
    onSuccess: () => {
      toast.success("Class updated");
      qc.invalidateQueries({ queryKey: USERS_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold">Class assignment</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Sets which class the student sees on their dashboard and which
          assignments are visible.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Class</Label>
          <Select value={cls} onValueChange={setCls}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CLASSES.map((c) => (
                <SelectItem key={c} value={String(c)}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label>Section</Label>
          <Select value={sec} onValueChange={setSec}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SECTIONS.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <SheetFooter className="-mx-5 -mb-4 mt-4">
        <Button
          onClick={() => save.mutate()}
          disabled={save.isPending}
          size="sm"
        >
          {save.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Save class
        </Button>
      </SheetFooter>
    </div>
  );
}

// ── Teacher editor (subjects + assigned classes) ─────────────────────────

function TeacherEditor({ user }: { user: AdminUser }) {
  const qc = useQueryClient();
  const userId = (user.id || user._id) as string;
  const [subjects, setSubjects] = React.useState<string[]>(
    user.subjects_taught || []
  );
  const [classes, setClasses] = React.useState<string[]>(
    user.assigned_classes || []
  );

  const save = useMutation({
    mutationFn: () => api.adminAssignTeacher(userId, subjects, classes),
    onSuccess: () => {
      toast.success("Teacher assignments saved");
      qc.invalidateQueries({ queryKey: USERS_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-semibold">Subjects</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          What this teacher can author assignments and questions in.
        </p>
        <Chips
          className="mt-3"
          options={SUBJECTS}
          selected={subjects}
          onChange={setSubjects}
        />
      </div>
      <div>
        <h3 className="text-sm font-semibold">Assigned classes</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Which class+section combinations this teacher can grade.
        </p>
        <Chips
          className="mt-3"
          options={ALL_CS}
          selected={classes}
          onChange={setClasses}
          compact
        />
      </div>
      <SheetFooter className="-mx-5 -mb-4 mt-2">
        <Button
          onClick={() => save.mutate()}
          disabled={save.isPending}
          size="sm"
        >
          {save.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Save assignments
        </Button>
      </SheetFooter>
    </div>
  );
}

function Chips({
  options,
  selected,
  onChange,
  compact = false,
  className,
}: {
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  compact?: boolean;
  className?: string;
}) {
  const toggle = (v: string) =>
    onChange(
      selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v]
    );
  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {options.map((opt) => {
        const sel = selected.includes(opt);
        return (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            className={cn(
              "rounded-md border px-2 py-0.5 transition-colors",
              compact ? "text-[11px]" : "text-xs",
              sel
                ? "border-primary bg-primary text-primary-foreground"
                : "border-border bg-surface text-foreground hover:bg-muted"
            )}
          >
            {opt}
          </button>
        );
      })}
    </div>
  );
}
