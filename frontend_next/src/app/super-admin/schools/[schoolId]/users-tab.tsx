"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const ROLE_FILTERS = [
  { value: "", label: "All" },
  { value: "admin", label: "Admin" },
  { value: "teacher", label: "Teacher" },
  { value: "student", label: "Student" },
];

const PAGE_SIZE = 50;

export function SuperAdminSchoolUsersTab({ schoolId }: { schoolId: number }) {
  const [role, setRole] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [openUserId, setOpenUserId] = React.useState<string | null>(null);

  React.useEffect(() => {
    setPage(1);
  }, [role]);

  const { data, isLoading } = useQuery({
    queryKey: ["super-admin-school-users", schoolId, role, page],
    queryFn: () =>
      api.superAdminSchoolUsers(schoolId, {
        role: role || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {ROLE_FILTERS.map((rf) => (
          <button
            key={rf.value}
            onClick={() => setRole(rf.value)}
            className={cn(
              "rounded-md border border-border px-3 py-1 text-xs font-medium transition-colors",
              role === rf.value
                ? "bg-primary-chip text-primary"
                : "bg-surface text-muted-foreground hover:text-foreground"
            )}
          >
            {rf.label}
          </button>
        ))}
        {data && (
          <span className="ml-auto text-xs text-muted-foreground tabular-nums">
            {data.total.toLocaleString()} users
          </span>
        )}
      </div>

      {isLoading || !data ? (
        <Skeleton className="h-64 w-full" />
      ) : data.users.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            No users match the current filter.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-5 py-3 font-medium">Name</th>
                  <th className="px-5 py-3 font-medium">Email</th>
                  <th className="px-5 py-3 font-medium">Role</th>
                  <th className="px-5 py-3 font-medium">Class</th>
                  <th className="px-5 py-3 font-medium">Last login</th>
                  <th className="px-5 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {data.users.map((u) => (
                  <React.Fragment key={u.id}>
                    <tr className="border-b border-border last:border-0 hover:bg-muted/30">
                      <td className="px-5 py-3 font-medium">
                        {u.full_name || u.username || "—"}
                      </td>
                      <td className="px-5 py-3 text-muted-foreground">
                        {u.email}
                      </td>
                      <td className="px-5 py-3">
                        <Badge variant="outline" className="text-[10px]">
                          {u.erp_title || u.role || "—"}
                        </Badge>
                      </td>
                      <td className="px-5 py-3 text-muted-foreground">
                        {u.class_section || "—"}
                      </td>
                      <td className="px-5 py-3 text-muted-foreground">
                        {u.last_login_at
                          ? new Date(u.last_login_at).toLocaleString()
                          : "Never"}
                      </td>
                      <td className="px-5 py-3 text-right">
                        <button
                          onClick={() =>
                            setOpenUserId(openUserId === u.id ? null : u.id)
                          }
                          className="text-xs font-medium text-primary hover:underline"
                        >
                          {openUserId === u.id ? "Hide usage" : "Usage"}
                        </button>
                      </td>
                    </tr>
                    {openUserId === u.id && (
                      <tr className="bg-muted/30">
                        <td colSpan={6} className="px-5 py-4">
                          <UserUsagePanel schoolId={schoolId} userId={u.id} />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {data && totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function UserUsagePanel({
  schoolId,
  userId,
}: {
  schoolId: number;
  userId: string;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["super-admin-user-usage", schoolId, userId],
    queryFn: () => api.superAdminUserUsage(schoolId, userId),
  });
  if (isLoading || !data)
    return <Skeleton className="h-20 w-full" />;

  const features = Array.from(
    new Set([
      ...Object.keys(data.today),
      ...Object.keys(data.last_7d),
      ...Object.keys(data.last_30d),
    ])
  ).sort();

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-muted-foreground">
            <th className="py-1 pr-3 font-medium">Feature</th>
            <th className="py-1 pr-3 font-medium tabular-nums">Today</th>
            <th className="py-1 pr-3 font-medium tabular-nums">7d</th>
            <th className="py-1 pr-3 font-medium tabular-nums">30d</th>
          </tr>
        </thead>
        <tbody>
          {features.map((f) => (
            <tr key={f}>
              <td className="py-1 pr-3">{f}</td>
              <td className="py-1 pr-3 tabular-nums">
                {(data.today[f] ?? 0).toLocaleString()}
              </td>
              <td className="py-1 pr-3 tabular-nums">
                {(data.last_7d[f] ?? 0).toLocaleString()}
              </td>
              <td className="py-1 pr-3 tabular-nums">
                {(data.last_30d[f] ?? 0).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
