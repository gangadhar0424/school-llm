"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Clock, FileText } from "lucide-react";
import { api } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
export const STUDENT_ASSIGNMENTS_KEY = ["student-assignments"] as const;

export function AssignmentsList() {
  const { data, isLoading } = useQuery({
    queryKey: STUDENT_ASSIGNMENTS_KEY,
    queryFn: api.studentAssignments,
  });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  const items = data?.assignments ?? [];
  if (items.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
          <FileText className="h-10 w-10 text-muted-foreground" />
          <p className="text-sm font-medium">No assignments yet</p>
          <p className="max-w-md text-xs text-muted-foreground">
            When your teacher publishes one, it&apos;ll appear here.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {items.map((a) => {
        const done = !!a.my_submission;
        return (
          <Card key={a.id} className="flex flex-col">
            <CardContent className="flex flex-1 flex-col gap-3 p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate text-base font-semibold">
                    {a.title}
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    {a.subject ? `${a.subject} · ` : ""}
                    Class {a.class_section} · {a.questions.length} question
                    {a.questions.length === 1 ? "" : "s"}
                  </p>
                </div>
                {done ? (
                  <Badge variant="success" className="gap-1">
                    <CheckCircle2 className="h-3 w-3" />
                    {Math.round(a.my_submission!.percent)}%
                  </Badge>
                ) : (
                  <Badge variant="warning" className="gap-1">
                    <Clock className="h-3 w-3" />
                    Pending
                  </Badge>
                )}
              </div>

              {a.description && (
                <p className="line-clamp-2 text-xs text-muted-foreground">
                  {a.description}
                </p>
              )}

              <div className="text-xs text-muted-foreground">
                {a.due_date ? (
                  <>Due: {new Date(a.due_date).toLocaleString()}</>
                ) : (
                  "No due date"
                )}
              </div>

              <div className="mt-auto flex justify-end">
                <Button asChild size="sm">
                  <Link href={`/student/assignments/${a.id}`}>
                    {done ? "View feedback →" : "Take assignment →"}
                  </Link>
                </Button>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
