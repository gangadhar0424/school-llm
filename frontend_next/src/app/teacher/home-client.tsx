"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ClipboardList, FilePlus, FileText, Users } from "lucide-react";
import { api } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { UsageCard } from "@/components/dashboard/usage-card";

export const TEACHER_ASSIGNMENTS_KEY = ["teacher-assignments"] as const;
export const TEACHER_STUDENTS_KEY = ["teacher-students"] as const;

export function TeacherHomeClient() {
  const { data: assignments, isLoading: aLoading } = useQuery({
    queryKey: TEACHER_ASSIGNMENTS_KEY,
    queryFn: api.teacherListAssignments,
  });
  const { data: students, isLoading: sLoading } = useQuery({
    queryKey: TEACHER_STUDENTS_KEY,
    queryFn: api.teacherListStudents,
  });

  const list = assignments?.assignments ?? [];
  const published = list.filter((a) => a.status === "published").length;
  const drafts = list.filter((a) => a.status === "draft").length;
  const total = list.length;
  const studentCount = students?.students?.length ?? 0;

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <UsageCard />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Assignments" value={total} icon={<FileText className="h-4 w-4" />} loading={aLoading} />
        <Stat label="Published" value={published} icon={<ClipboardList className="h-4 w-4 text-success" />} loading={aLoading} />
        <Stat label="Drafts" value={drafts} icon={<FilePlus className="h-4 w-4 text-warning" />} loading={aLoading} />
        <Stat label="Students" value={studentCount} icon={<Users className="h-4 w-4" />} loading={sLoading} />
      </div>

      <div className="flex flex-wrap gap-3">
        <Button asChild>
          <Link href="/teacher/new-assignment">
            <FilePlus className="h-4 w-4" /> New assignment
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/teacher/assignments">
            <FileText className="h-4 w-4" /> My assignments
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/teacher/students">
            <Users className="h-4 w-4" /> My students
          </Link>
        </Button>
      </div>

      <section>
        <h2 className="mb-3 text-base font-semibold">Recent assignments</h2>
        {aLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : list.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              You haven&apos;t created any assignments yet.
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-2">
            {list.slice(0, 5).map((a) => (
              <Card key={a.id}>
                <CardContent className="flex items-center justify-between gap-3 p-4">
                  <div className="min-w-0">
                    <Link
                      href={`/teacher/assignments/${a.id}`}
                      className="truncate text-sm font-medium hover:underline"
                    >
                      {a.title}
                    </Link>
                    <p className="text-xs text-muted-foreground">
                      Class {a.class_section}
                      {a.subject ? ` · ${a.subject}` : ""} · {a.questions.length} Q
                      · {a.submission_count ?? 0} submissions
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
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  icon,
  loading,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
  loading?: boolean;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          {icon} {label}
        </div>
        <div className="mt-1 text-2xl font-bold">
          {loading ? <Skeleton className="h-7 w-12" /> : value}
        </div>
      </CardContent>
    </Card>
  );
}
