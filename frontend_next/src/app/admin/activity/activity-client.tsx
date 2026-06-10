"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { formatRelative } from "@/lib/utils";

export function AdminActivityClient() {
  const [email, setEmail] = React.useState("");
  const [debouncedEmail, setDebouncedEmail] = React.useState("");

  React.useEffect(() => {
    const t = setTimeout(() => setDebouncedEmail(email.trim()), 350);
    return () => clearTimeout(t);
  }, [email]);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-activity", debouncedEmail],
    queryFn: () =>
      api.adminGetActivity({
        limit: 200,
        user_email: debouncedEmail || undefined,
      }),
  });

  const rows = data?.activities ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4">
          <Input
            placeholder="Filter by user email…"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </CardContent>
      </Card>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : rows.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No activity matched.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <ul className="divide-y divide-border">
              {rows.map((row, i) => (
                <li
                  key={i}
                  className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium">
                      {row.user_email}{" "}
                      <Badge variant="outline" className="ml-1 text-[10px]">
                        {row.activity_type}
                      </Badge>
                    </p>
                    {row.details && (
                      <p className="truncate text-xs text-muted-foreground">
                        {typeof row.details === "string"
                          ? row.details
                          : JSON.stringify(row.details)}
                      </p>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {formatRelative(row.timestamp)}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
