"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import type { Role } from "@/lib/types";

const PERMISSIONS_KEY = ["admin-permissions"] as const;
const ROLES: Role[] = ["admin", "teacher", "student"];

// Human labels for known features. Anything we don't know about falls
// back to the raw key — admins can still toggle it.
const FEATURE_LABELS: Record<string, { icon: string; label: string }> = {
  manage_users: { icon: "👥", label: "Manage users" },
  view_audit_logs: { icon: "📋", label: "View audit logs" },
  view_analytics: { icon: "📊", label: "View analytics" },
  export_data: { icon: "📥", label: "Export data" },
  assign_class_section: { icon: "🎓", label: "Assign class/section" },
  assign_teacher_subjects: {
    icon: "📚",
    label: "Assign teacher subjects/classes",
  },
  toggle_user_status: { icon: "🔌", label: "Activate / deactivate users" },
  create_assignments: { icon: "➕", label: "Create assignments" },
  edit_assignments: { icon: "✏️", label: "Edit assignments" },
  override_grading: { icon: "✋", label: "Override AI grading" },
  view_submissions: { icon: "👀", label: "View submissions" },
  submit_assignments: { icon: "📤", label: "Submit assignments" },
  view_own_grades: { icon: "📈", label: "View own grades" },
  change_password: { icon: "🔑", label: "Change own password" },
  upload_pdfs: { icon: "📄", label: "Upload PDFs" },
  use_ai_tools: { icon: "🤖", label: "Use AI tools" },
};

export function AdminPermissionsClient() {
  const qc = useQueryClient();
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

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!data) return null;

  // Build the union of all features across roles so the matrix is dense.
  const allFeatures = Array.from(
    new Set(
      ROLES.flatMap((r) => Object.keys(data.permissions[r] || {}))
    )
  ).sort();

  return (
    <Card>
      <CardContent className="p-0">
        <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-4 gap-y-2 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <span>Feature</span>
          <span className="text-center">Admin</span>
          <span className="text-center">Teacher</span>
          <span className="text-center">Student</span>
        </div>
        <div className="divide-y divide-border">
          {allFeatures.map((feat) => {
            const meta = FEATURE_LABELS[feat] || { icon: "⚙️", label: feat };
            return (
              <div
                key={feat}
                className="grid grid-cols-[1fr_auto_auto_auto] items-center gap-x-4 px-4 py-3"
              >
                <div className="text-sm">
                  <span className="mr-2">{meta.icon}</span>
                  {meta.label}
                </div>
                {ROLES.map((role) => (
                  <div key={role} className="flex justify-center">
                    <Switch
                      checked={!!data.permissions[role]?.[feat]}
                      onCheckedChange={(enabled) =>
                        set.mutate({ role, feature: feat, enabled })
                      }
                    />
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
