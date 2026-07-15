"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { SuperAdminSchoolAnalyticsTab } from "./analytics-tab";
import { SuperAdminSchoolUsersTab } from "./users-tab";
import { SuperAdminSchoolRateLimitsTab } from "./rate-limits-tab";

type Tab = "analytics" | "users" | "rate-limits";

export function SuperAdminSchoolDetailClient({
  schoolId,
}: {
  schoolId: number;
}) {
  const [tab, setTab] = React.useState<Tab>("analytics");
  const { data } = useQuery({
    queryKey: ["super-admin-school-detail", schoolId],
    queryFn: () => api.superAdminSchoolDetail(schoolId),
  });

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="p-5">
          {data ? (
            <>
              <div className="flex flex-wrap items-baseline gap-3">
                <h2 className="text-lg font-semibold">{data.school.name}</h2>
                <span className="text-xs text-muted-foreground">
                  ID {data.school.school_id}
                </span>
                <Badge variant="outline" className="text-[10px] uppercase tracking-wider">
                  {data.school.plan || data.school_plan || "No ERP plan"}
                </Badge>
              </div>
              <div className="mt-3 flex flex-wrap gap-4 text-sm text-muted-foreground">
                <span>
                  <strong className="text-foreground tabular-nums">
                    {data.counts.admin}
                  </strong>{" "}
                  admins
                </span>
                <span>
                  <strong className="text-foreground tabular-nums">
                    {data.counts.teacher}
                  </strong>{" "}
                  teachers
                </span>
                <span>
                  <strong className="text-foreground tabular-nums">
                    {data.counts.student}
                  </strong>{" "}
                  students
                </span>
                <span>
                  <strong className="text-foreground tabular-nums">
                    {Object.values(data.ai_usage_7d).reduce((a, b) => a + b, 0)}
                  </strong>{" "}
                  AI calls (7d)
                </span>
              </div>
            </>
          ) : (
            <Skeleton className="h-16 w-full" />
          )}
        </CardContent>
      </Card>

      <div
        role="tablist"
        aria-label="Tabs"
        className="inline-flex items-center rounded-md border border-border bg-surface p-0.5"
      >
        <TabBtn
          current={tab}
          value="analytics"
          onClick={() => setTab("analytics")}
        >
          Analytics
        </TabBtn>
        <TabBtn current={tab} value="users" onClick={() => setTab("users")}>
          Users
        </TabBtn>
        <TabBtn
          current={tab}
          value="rate-limits"
          onClick={() => setTab("rate-limits")}
        >
          Rate limits
        </TabBtn>
      </div>

      {tab === "analytics" && (
        <SuperAdminSchoolAnalyticsTab schoolId={schoolId} />
      )}
      {tab === "users" && <SuperAdminSchoolUsersTab schoolId={schoolId} />}
      {tab === "rate-limits" && (
        <SuperAdminSchoolRateLimitsTab schoolId={schoolId} />
      )}
    </div>
  );
}

function TabBtn({
  current,
  value,
  onClick,
  children,
}: {
  current: Tab;
  value: Tab;
  onClick: () => void;
  children: React.ReactNode;
}) {
  const active = current === value;
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "rounded-sm px-3 py-1 text-xs font-medium transition-colors",
        active
          ? "bg-primary-chip text-primary"
          : "text-muted-foreground hover:text-foreground"
      )}
    >
      {children}
    </button>
  );
}
