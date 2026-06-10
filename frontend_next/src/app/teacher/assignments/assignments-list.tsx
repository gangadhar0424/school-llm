"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Send, Lock, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { TEACHER_ASSIGNMENTS_KEY } from "../home-client";

export function TeacherAssignmentsList() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: TEACHER_ASSIGNMENTS_KEY,
    queryFn: api.teacherListAssignments,
  });

  const publish = useMutation({
    mutationFn: (id: string) =>
      api.teacherUpdateAssignment(id, { status: "published" }),
    onSuccess: () => {
      toast.success("Published.");
      qc.invalidateQueries({ queryKey: TEACHER_ASSIGNMENTS_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });
  const close = useMutation({
    mutationFn: (id: string) =>
      api.teacherUpdateAssignment(id, { status: "closed" }),
    onSuccess: () => {
      toast.success("Closed.");
      qc.invalidateQueries({ queryKey: TEACHER_ASSIGNMENTS_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });
  const del = useMutation({
    mutationFn: (id: string) => api.teacherDeleteAssignment(id),
    onSuccess: () => {
      toast.success("Deleted.");
      qc.invalidateQueries({ queryKey: TEACHER_ASSIGNMENTS_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  if (isLoading) return <Skeleton className="h-32 w-full" />;
  const items = data?.assignments ?? [];
  if (items.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
          <p className="text-sm font-medium">No assignments yet</p>
          <Button asChild>
            <Link href="/teacher/new-assignment">Create your first</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-3">
      {items.map((a) => (
        <Card key={a.id}>
          <CardContent className="space-y-3 p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <Link
                  href={`/teacher/assignments/${a.id}`}
                  className="text-base font-semibold hover:underline"
                >
                  {a.title}
                </Link>
                <p className="text-xs text-muted-foreground">
                  Class {a.class_section}
                  {a.subject ? ` · ${a.subject}` : ""} · {a.questions.length} Q
                  · {a.submission_count ?? 0} submissions
                  {a.due_date && ` · Due ${new Date(a.due_date).toLocaleString()}`}
                </p>
              </div>
              <Badge
                variant={
                  a.status === "published"
                    ? "success"
                    : a.status === "draft"
                      ? "warning"
                      : "outline"
                }
              >
                {a.status}
              </Badge>
            </div>
            {a.description && (
              <p className="text-xs text-muted-foreground">{a.description}</p>
            )}
            <div className="flex flex-wrap gap-2">
              {a.status === "draft" && (
                <Button
                  size="sm"
                  onClick={() => publish.mutate(a.id)}
                  disabled={publish.isPending}
                >
                  <Send className="h-3.5 w-3.5" /> Publish
                </Button>
              )}
              {a.status === "published" && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => close.mutate(a.id)}
                  disabled={close.isPending}
                >
                  <Lock className="h-3.5 w-3.5" /> Close
                </Button>
              )}
              <Button asChild size="sm" variant="outline">
                <Link href={`/teacher/assignments/${a.id}`}>View submissions →</Link>
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="text-danger hover:bg-danger/10"
                onClick={() => {
                  if (confirm(`Delete "${a.title}"?`)) del.mutate(a.id);
                }}
                disabled={del.isPending}
              >
                <Trash2 className="h-3.5 w-3.5" /> Delete
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
