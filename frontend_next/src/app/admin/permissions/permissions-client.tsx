"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpenCheck,
  Cpu,
  Loader2,
  RotateCcw,
  Search,
  Settings2,
  UserCog,
} from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Role } from "@/lib/types";

const PERMISSIONS_KEY = ["admin-permissions"] as const;
const ROLES: Role[] = ["admin", "teacher", "student"];

/** Per-feature display metadata: short label + one-line description. */
const FEATURE_META: Record<
  string,
  { label: string; description: string }
> = {
  manage_users: {
    label: "Manage users",
    description: "View and edit any user account.",
  },
  toggle_user_status: {
    label: "Activate / deactivate users",
    description: "Flip the is_active flag on user accounts.",
  },
  view_audit_logs: {
    label: "View activity logs",
    description: "Browse the audit trail of every user action.",
  },
  view_analytics: {
    label: "View analytics",
    description: "Access system-wide usage metrics and charts.",
  },
  export_data: {
    label: "Export data",
    description: "Download activity logs as CSV.",
  },
  assign_class_section: {
    label: "Assign class/section",
    description: "Set a student's class and section.",
  },
  assign_teacher_subjects: {
    label: "Assign teacher subjects/classes",
    description: "Map teachers to subjects and classes.",
  },
  create_assignments: {
    label: "Create assignments",
    description: "Author new assignments for assigned classes.",
  },
  edit_assignments: {
    label: "Edit assignments",
    description: "Modify existing assignment metadata or questions.",
  },
  override_grading: {
    label: "Override AI grading",
    description: "Replace AI-assigned grades on student submissions.",
  },
  view_submissions: {
    label: "View submissions",
    description: "See student submissions for assignments they own.",
  },
  submit_assignments: {
    label: "Submit assignments",
    description: "Submit answers to teacher-assigned work.",
  },
  view_own_grades: {
    label: "View own grades",
    description: "See feedback and scores on submitted work.",
  },
  change_password: {
    label: "Change own password",
    description: "Update the password on this account.",
  },
  upload_pdfs: {
    label: "Upload PDFs",
    description: "Add new PDF documents to the platform.",
  },
  use_ai_tools: {
    label: "Use AI tools",
    description: "Run Q&A, quizzes, summaries, audio, and video.",
  },
};

/** Logical groups so the long flat list reads as a hierarchy. */
const FEATURE_GROUPS: {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  features: string[];
}[] = [
  {
    id: "system",
    label: "System administration",
    icon: Settings2,
    features: [
      "manage_users",
      "toggle_user_status",
      "view_audit_logs",
      "view_analytics",
      "export_data",
      "assign_class_section",
      "assign_teacher_subjects",
    ],
  },
  {
    id: "assignments",
    label: "Assignments & grading",
    icon: BookOpenCheck,
    features: [
      "create_assignments",
      "edit_assignments",
      "override_grading",
      "view_submissions",
      "submit_assignments",
      "view_own_grades",
    ],
  },
  {
    id: "ai",
    label: "AI features",
    icon: Cpu,
    features: ["upload_pdfs", "use_ai_tools"],
  },
  {
    id: "account",
    label: "Account",
    icon: UserCog,
    features: ["change_password"],
  },
];

export function AdminPermissionsClient() {
  const qc = useQueryClient();
  const [search, setSearch] = React.useState("");

  const { data, isLoading } = useQuery({
    queryKey: PERMISSIONS_KEY,
    queryFn: api.adminGetPermissions,
  });

  const set = useMutation({
    mutationFn: ({
      role,
      feature,
      enabled,
    }: {
      role: Role;
      feature: string;
      enabled: boolean;
    }) => api.adminSetPermission(role, feature, enabled),
    onMutate: async ({ role, feature, enabled }) => {
      await qc.cancelQueries({ queryKey: PERMISSIONS_KEY });
      const prev = qc.getQueryData(PERMISSIONS_KEY);
      qc.setQueryData(PERMISSIONS_KEY, (old) => {
        if (!old) return old;
        const next = JSON.parse(JSON.stringify(old)) as typeof data;
        if (next && next.permissions[role]) {
          next.permissions[role][feature] = enabled;
        }
        return next;
      });
      return { prev };
    },
    onError: (e: ApiError, _vars, ctx) => {
      qc.setQueryData(PERMISSIONS_KEY, ctx?.prev);
      toast.error(e.message);
    },
    onSuccess: (_data, { feature, enabled }) => {
      toast.success(`${feature} ${enabled ? "enabled" : "disabled"}.`);
    },
  });

  const reset = useMutation({
    mutationFn: (role: Role) => api.adminResetRolePermissions(role),
    onSuccess: (resp, role) => {
      // Backend returns the merged post-reset map, so we can update
      // the cache without an extra GET round-trip.
      qc.setQueryData(PERMISSIONS_KEY, { permissions: resp.permissions });
      toast.success(`${role} permissions reset to defaults.`);
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  const onResetRole = (role: Role) => {
    if (
      window.confirm(
        `Reset ALL ${role} permissions to defaults? Any toggles you've changed for this role will be undone.`
      )
    ) {
      reset.mutate(role);
    }
  };

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!data) return null;

  // Union of every feature the backend knows about. Anything not
  // pre-registered in FEATURE_GROUPS lands in an "Other" group so
  // admins can still toggle it.
  const allFeatures = Array.from(
    new Set(ROLES.flatMap((r) => Object.keys(data.permissions[r] || {})))
  );
  const known = new Set(FEATURE_GROUPS.flatMap((g) => g.features));
  const other = allFeatures.filter((f) => !known.has(f)).sort();

  const groups: typeof FEATURE_GROUPS = [...FEATURE_GROUPS];
  if (other.length > 0) {
    groups.push({
      id: "other",
      label: "Other",
      icon: Settings2,
      features: other,
    });
  }

  // Search: filter features by label/description/key match.
  const q = search.trim().toLowerCase();
  const matches = (feat: string) => {
    if (!q) return true;
    const meta = FEATURE_META[feat];
    return (
      feat.toLowerCase().includes(q) ||
      meta?.label.toLowerCase().includes(q) ||
      meta?.description.toLowerCase().includes(q)
    );
  };

  const visibleByGroup = groups.map((g) => ({
    ...g,
    visible: g.features.filter((f) => allFeatures.includes(f)).filter(matches),
  }));
  const totalVisible = visibleByGroup.reduce(
    (acc, g) => acc + g.visible.length,
    0
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1 sm:max-w-md">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search permissions…"
            className="h-9 pl-8"
          />
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
            Reset
          </span>
          {ROLES.map((role) => {
            const isPending =
              reset.isPending && reset.variables === role;
            return (
              <Button
                key={role}
                variant="outline"
                size="sm"
                className="h-8 capitalize"
                onClick={() => onResetRole(role)}
                disabled={reset.isPending}
              >
                {isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <RotateCcw className="h-3 w-3" />
                )}
                {role}
              </Button>
            );
          })}
        </div>
      </div>

      {visibleByGroup.map((group) => {
        if (group.visible.length === 0) return null;
        const Icon = group.icon;
        return (
          <section key={group.id} className="space-y-2">
            <h2 className="flex items-center gap-2 px-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
              <Icon className="h-3 w-3" />
              {group.label}
            </h2>
            <Card>
              <CardContent className="p-0">
                <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-6 border-b border-border bg-surface-2 px-4 py-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  <span>Feature</span>
                  <span className="w-12 text-center">Admin</span>
                  <span className="w-12 text-center">Teacher</span>
                  <span className="w-12 text-center">Student</span>
                </div>
                <div className="divide-y divide-border">
                  {group.visible.map((feat) => {
                    const meta = FEATURE_META[feat] || {
                      label: feat,
                      description: "",
                    };
                    return (
                      <div
                        key={feat}
                        className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-x-6 px-4 py-3 transition-colors hover:bg-muted/40"
                      >
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-foreground">
                            {meta.label}
                          </div>
                          {meta.description && (
                            <div className="mt-0.5 text-xs text-muted-foreground">
                              {meta.description}
                            </div>
                          )}
                        </div>
                        {ROLES.map((role) => (
                          <div
                            key={role}
                            className={cn(
                              "flex w-12 justify-center",
                              !data.permissions[role]?.[feat] && "opacity-70"
                            )}
                          >
                            <Switch
                              checked={!!data.permissions[role]?.[feat]}
                              onCheckedChange={(enabled) =>
                                set.mutate({ role, feature: feat, enabled })
                              }
                              aria-label={`${meta.label} for ${role}`}
                            />
                          </div>
                        ))}
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          </section>
        );
      })}

      {q && totalVisible === 0 && (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No permissions match &quot;{search}&quot;.
          </CardContent>
        </Card>
      )}
    </div>
  );
}
