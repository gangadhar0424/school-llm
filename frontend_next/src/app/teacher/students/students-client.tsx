"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { TEACHER_STUDENTS_KEY } from "../home-client";
import { formatRelative } from "@/lib/utils";
import type { TeacherStudent } from "@/lib/types";

export function TeacherStudentsClient() {
  const { data, isLoading } = useQuery({
    queryKey: TEACHER_STUDENTS_KEY,
    queryFn: api.teacherListStudents,
  });

  if (isLoading) return <Skeleton className="h-32 w-full" />;
  const byClass = data?.by_class ?? {};
  const classes = Object.keys(byClass).sort();

  if (classes.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          No students in your assigned classes yet.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {classes.map((cs) => (
        <section key={cs}>
          <h2 className="mb-2 text-sm font-semibold">
            Class {cs}{" "}
            <Badge variant="outline" className="ml-2">
              {byClass[cs].length} students
            </Badge>
          </h2>
          <div className="grid gap-2">
            {byClass[cs].map((s) => (
              <StudentCard key={s.id} student={s} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function StudentCard({ student }: { student: TeacherStudent }) {
  const [open, setOpen] = React.useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["teacher-student-subs", student.id],
    queryFn: () => api.teacherStudentSubmissions(student.id),
    enabled: open,
  });

  return (
    <Card>
      <CardContent className="p-4">
        <button
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between text-left"
        >
          <span>
            <span className="text-sm font-medium">
              👨‍🎓 {student.full_name || student.username}
            </span>
            <span className="ml-2 text-xs text-muted-foreground">
              · {student.email}
            </span>
          </span>
          <span className="text-xs text-muted-foreground">
            {open ? "▲" : "▼"}
          </span>
        </button>
        {open && (
          <div className="mt-3 border-t border-border pt-3">
            {isLoading ? (
              <Skeleton className="h-16 w-full" />
            ) : (data?.submissions.length ?? 0) === 0 ? (
              <p className="py-2 text-xs text-muted-foreground">
                No submissions yet.
              </p>
            ) : (
              <ul className="space-y-1 text-xs">
                {data!.submissions.map((s) => {
                  const pct = Math.round(s.percent || 0);
                  return (
                    <li
                      key={s.id}
                      className="flex items-center justify-between"
                    >
                      <span className="truncate">
                        {s.assignment_title || s.assignment_id || "(assignment)"}{" "}
                        · {formatRelative(s.submitted_at)}
                      </span>
                      <Badge
                        variant={pct >= 80 ? "success" : pct >= 50 ? "warning" : "danger"}
                      >
                        {s.total_score.toFixed(1)} / {s.total_max} · {pct}%
                      </Badge>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
