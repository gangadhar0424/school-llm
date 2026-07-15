"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, Sliders } from "lucide-react";
import { api } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

export function SuperAdminSchoolsClient() {
  const { data, isLoading } = useQuery({
    queryKey: ["super-admin-schools"],
    queryFn: api.superAdminSchools,
  });

  if (isLoading || !data) return <Skeleton className="h-64 w-full" />;

  if (data.schools.length === 0) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">
          No schools have signed in yet. Once a user from a school logs in,
          the school will appear here.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted-foreground">
              <th className="px-5 py-3 font-medium">School</th>
              <th className="px-5 py-3 font-medium">Plan</th>
              <th className="px-5 py-3 font-medium tabular-nums">Users</th>
              <th className="px-5 py-3 font-medium tabular-nums">AI calls (7d)</th>
              <th className="px-5 py-3 font-medium">First seen</th>
              <th className="px-5 py-3 font-medium">Last seen</th>
              <th className="px-5 py-3 font-medium">Limits</th>
              <th className="px-5 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {data.schools.map((s) => (
              <tr
                key={s.school_id ?? Math.random()}
                className="border-b border-border last:border-0 hover:bg-muted/30"
              >
                <td className="px-5 py-3">
                  <div className="flex flex-col">
                    <span className="font-medium text-foreground">
                      {s.name}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      ID {s.school_id ?? "—"}
                    </span>
                  </div>
                </td>
                <td className="px-5 py-3">
                  {s.plan ? (
                    <Badge variant="outline" className="text-[10px] uppercase tracking-wider">
                      {s.plan}
                    </Badge>
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </td>
                <td className="px-5 py-3 tabular-nums">
                  {s.user_count.toLocaleString()}
                </td>
                <td className="px-5 py-3 tabular-nums">
                  {s.ai_calls_7d.toLocaleString()}
                </td>
                <td className="px-5 py-3 text-muted-foreground">
                  {formatDate(s.first_seen_at)}
                </td>
                <td className="px-5 py-3 text-muted-foreground">
                  {formatDate(s.last_seen_at)}
                </td>
                <td className="px-5 py-3">
                  {s.has_rate_limit_override ? (
                    <Badge variant="outline" className="gap-1 text-[10px]">
                      <Sliders className="h-3 w-3" />
                      Custom
                    </Badge>
                  ) : (
                    <span className="text-xs text-muted-foreground">
                      Default
                    </span>
                  )}
                </td>
                <td className="px-5 py-3 text-right">
                  {s.school_id !== null && (
                    <Link
                      href={`/super-admin/schools/${s.school_id}`}
                      className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                    >
                      Open
                      <ChevronRight className="h-3 w-3" />
                    </Link>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
