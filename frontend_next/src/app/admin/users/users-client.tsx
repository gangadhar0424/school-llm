"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Search } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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

  const { data, isLoading } = useQuery({
    queryKey: USERS_KEY,
    queryFn: api.adminGetUsers,
  });

  const users = (data?.users ?? []).filter((u) => {
    if (roleFilter !== "all" && u.role !== roleFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      if (!u.email.toLowerCase().includes(q) && !u.username.toLowerCase().includes(q))
        return false;
    }
    return true;
  });

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by email or username…"
              className="pl-8"
            />
          </div>
          <Select
            value={roleFilter}
            onValueChange={(v) => setRoleFilter(v as Role | "all")}
          >
            <SelectTrigger className="sm:w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROLES.map((r) => (
                <SelectItem key={r} value={r}>
                  {r === "all" ? "All roles" : r}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <div className="space-y-2">
          {users.length === 0 && (
            <Card>
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                No users matched your filters.
              </CardContent>
            </Card>
          )}
          {users.map((u) => (
            <UserRow key={u.id || u.email} user={u} />
          ))}
        </div>
      )}
    </div>
  );
}

function UserRow({ user }: { user: AdminUser }) {
  const qc = useQueryClient();
  const userId = (user.id || user._id) as string;
  const [editing, setEditing] = React.useState(false);

  const toggle = useMutation({
    mutationFn: () => api.adminUpdateUserStatus(userId, !user.is_active),
    onSuccess: () => {
      toast.success(user.is_active ? "Deactivated" : "Activated");
      qc.invalidateQueries({ queryKey: USERS_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium">
                {user.full_name || user.username}
              </span>
              <Badge variant={user.is_active ? "success" : "outline"}>
                {user.is_active ? "Active" : "Inactive"}
              </Badge>
              <Badge variant="outline">{user.role}</Badge>
            </div>
            <p className="text-xs text-muted-foreground">{user.email}</p>
            <div className="mt-1 text-[11px] text-muted-foreground">
              {user.role === "student"
                ? `Class ${user.class_section || `${user.class_level ?? "—"}${user.section ?? ""}`}`
                : user.role === "teacher"
                  ? `${user.subjects_taught?.join(", ") || "no subjects"} · classes ${user.assigned_classes?.join(", ") || "—"}`
                  : "Full system access"}{" "}
              · joined {formatRelative(user.created_at)} · last login{" "}
              {user.last_login ? formatRelative(user.last_login) : "never"} ·{" "}
              {user.login_count ?? 0} sign-ins
            </div>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setEditing((v) => !v)}
            >
              {editing ? "Cancel" : "✎ Edit"}
            </Button>
            <Button
              size="sm"
              variant={user.is_active ? "outline" : "default"}
              onClick={() => toggle.mutate()}
              disabled={toggle.isPending}
            >
              {toggle.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : user.is_active ? (
                "Deactivate"
              ) : (
                "Activate"
              )}
            </Button>
          </div>
        </div>
        {editing && (
          <div className="mt-3 border-t border-border pt-3">
            {user.role === "student" && <StudentClassEditor user={user} />}
            {user.role === "teacher" && <TeacherEditor user={user} />}
            {user.role === "admin" && (
              <p className="text-xs text-muted-foreground">
                Admins have full system access — no per-class assignments.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

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
    <div className="flex flex-wrap items-end gap-2">
      <div>
        <p className="text-xs text-muted-foreground">Class</p>
        <Select value={cls} onValueChange={setCls}>
          <SelectTrigger className="w-20">
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
        <p className="text-xs text-muted-foreground">Section</p>
        <Select value={sec} onValueChange={setSec}>
          <SelectTrigger className="w-20">
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
      <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
        Save class
      </Button>
    </div>
  );
}

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
    <div className="space-y-3">
      <div>
        <p className="text-xs text-muted-foreground">Subjects taught</p>
        <Chips
          options={SUBJECTS}
          selected={subjects}
          onChange={setSubjects}
        />
      </div>
      <div>
        <p className="text-xs text-muted-foreground">Assigned classes</p>
        <Chips
          options={ALL_CS}
          selected={classes}
          onChange={setClasses}
          compact
        />
      </div>
      <Button size="sm" onClick={() => save.mutate()} disabled={save.isPending}>
        Save assignments
      </Button>
    </div>
  );
}

function Chips({
  options,
  selected,
  onChange,
  compact = false,
}: {
  options: string[];
  selected: string[];
  onChange: (next: string[]) => void;
  compact?: boolean;
}) {
  const toggle = (v: string) =>
    onChange(
      selected.includes(v) ? selected.filter((x) => x !== v) : [...selected, v]
    );
  return (
    <div className="flex flex-wrap gap-1">
      {options.map((opt) => {
        const sel = selected.includes(opt);
        return (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            className={cn(
              "rounded-full border px-2 py-0.5",
              compact ? "text-[10px]" : "text-xs",
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
