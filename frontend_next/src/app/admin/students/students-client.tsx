"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, Search, Users as UsersIcon } from "lucide-react";
import { api } from "@/lib/client-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { DataTable, type DataTableColumn } from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Sparkline } from "@/components/ui/sparkline";
import { ExportButton } from "@/components/admin/export-button";
import { csvDate, type ExportColumn } from "@/lib/csv-export";
import { useCurrentUser } from "@/lib/use-current-user";
import { formatRelative } from "@/lib/utils";
import type { StudentListRow } from "@/lib/types";

const ALL = "__all__";

export function AdminStudentsClient() {
  const user = useCurrentUser();
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-students"],
    queryFn: () => api.adminListStudents(),
    staleTime: 30_000,
  });

  const [search, setSearch] = React.useState("");
  const [classFilter, setClassFilter] = React.useState<string>(ALL);
  const [sectionFilter, setSectionFilter] = React.useState<string>(ALL);
  const [classTeacherFilter, setClassTeacherFilter] = React.useState<string>(ALL);
  const [activeId, setActiveId] = React.useState<string | null>(null);

  // Stable reference for downstream useMemo — `data?.students ?? []`
  // creates a new array every render, defeating the memoization.
  const students = React.useMemo(() => data?.students ?? [], [data]);

  const { classOptions, sectionOptions, teacherOptions } = React.useMemo(() => {
    const cls = new Set<string>();
    const sec = new Set<string>();
    const teach = new Map<string, string>();
    for (const row of students) {
      if (row.class_section) {
        cls.add(row.class_section);
        // Extract the trailing letter section ("8A" → "A").
        const m = row.class_section.match(/[A-Z]+$/i);
        if (m) sec.add(m[0].toUpperCase());
      }
      if (row.class_teacher_id && row.class_teacher_name) {
        teach.set(row.class_teacher_id, row.class_teacher_name);
      }
    }
    return {
      classOptions: [...cls].sort(),
      sectionOptions: [...sec].sort(),
      teacherOptions: [...teach.entries()]
        .map(([id, name]) => ({ id, name }))
        .sort((a, b) => a.name.localeCompare(b.name)),
    };
  }, [students]);

  const filtered = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    return students.filter((s) => {
      if (q && !`${s.full_name} ${s.email}`.toLowerCase().includes(q)) return false;
      if (classFilter !== ALL && s.class_section !== classFilter) return false;
      if (sectionFilter !== ALL) {
        const m = (s.class_section ?? "").match(/[A-Z]+$/i);
        if (!m || m[0].toUpperCase() !== sectionFilter) return false;
      }
      if (classTeacherFilter !== ALL && s.class_teacher_id !== classTeacherFilter) {
        return false;
      }
      return true;
    });
  }, [students, search, classFilter, sectionFilter, classTeacherFilter]);

  // 7.2 — auto-hide the Class Teacher column if no student in scope has
  // a class teacher resolved.
  const showClassTeacherCol = students.some((s) => !!s.class_teacher_name);

  const columns: DataTableColumn<StudentListRow>[] = [
    {
      key: "name",
      header: "Name",
      sortable: true,
      sortValue: (r) => r.full_name.toLowerCase(),
      cell: (r) => (
        <div className="min-w-0">
          <div className="truncate font-medium text-foreground">{r.full_name}</div>
          <div className="truncate text-xs text-muted-foreground">{r.email}</div>
        </div>
      ),
    },
    {
      key: "class",
      header: "Class",
      sortable: true,
      sortValue: (r) => r.class_section ?? "",
      width: "w-24",
      cell: (r) =>
        r.class_section ? (
          <Badge variant="secondary">{r.class_section}</Badge>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        ),
    },
    ...(showClassTeacherCol
      ? [{
          key: "class_teacher",
          header: "Class teacher",
          sortable: true,
          sortValue: (r: StudentListRow) => r.class_teacher_name ?? "",
          cell: (r: StudentListRow) =>
            r.class_teacher_name ? (
              <span className="text-sm">{r.class_teacher_name}</span>
            ) : (
              <span className="text-xs text-muted-foreground">—</span>
            ),
        }]
      : []),
    {
      key: "ai_30d",
      header: "AI · 30d",
      sortable: true,
      sortValue: (r) => r.ai_sessions_30d,
      width: "w-28",
      align: "right",
      cell: (r) => (
        <span className="tabular-nums">{r.ai_sessions_30d.toLocaleString()}</span>
      ),
    },
    {
      key: "last_active",
      header: "Last active",
      sortable: true,
      sortValue: (r) => r.last_active ?? "",
      width: "w-40",
      cell: (r) =>
        r.last_active ? (
          <span className="text-xs text-muted-foreground">
            {formatRelative(r.last_active)}
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">never</span>
        ),
    },
  ];

  const initialSorted = React.useMemo(() => {
    return [...filtered].sort((a, b) =>
      (b.last_active ?? "").localeCompare(a.last_active ?? "")
    );
  }, [filtered]);

  const exportColumns: ExportColumn<StudentListRow>[] = React.useMemo(
    () => [
      { header: "Name", value: (r) => r.full_name },
      { header: "Email", value: (r) => r.email },
      { header: "Class section", value: (r) => r.class_section ?? "" },
      { header: "Class teacher", value: (r) => r.class_teacher_name ?? "" },
      { header: "AI sessions (30 days)", value: (r) => r.ai_sessions_30d },
      { header: "Last active", value: (r) => csvDate(r.last_active) },
    ],
    []
  );

  const activeFilters = React.useMemo(() => {
    const bits: string[] = [];
    if (search) bits.push(`search="${search}"`);
    if (classFilter !== ALL) bits.push(`class=${classFilter}`);
    if (sectionFilter !== ALL) bits.push(`section=${sectionFilter}`);
    if (classTeacherFilter !== ALL) bits.push(`class_teacher_id=${classTeacherFilter}`);
    return bits.length === 0 ? "none" : bits.join(", ");
  }, [search, classFilter, sectionFilter, classTeacherFilter]);

  if (error) {
    return (
      <Card>
        <CardContent className="p-6">
          <EmptyState
            icon={<BookOpen className="h-5 w-5" />}
            title="Couldn't load the students list"
            description={String((error as Error).message)}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or email…"
              className="h-9 pl-8"
            />
          </div>
          {classOptions.length > 0 && (
            <Select value={classFilter} onValueChange={setClassFilter}>
              <SelectTrigger className="h-9 sm:w-32">
                <SelectValue placeholder="Class" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All classes</SelectItem>
                {classOptions.map((c) => (
                  <SelectItem key={c} value={c}>
                    {c}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {sectionOptions.length > 0 && (
            <Select value={sectionFilter} onValueChange={setSectionFilter}>
              <SelectTrigger className="h-9 sm:w-28">
                <SelectValue placeholder="Section" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All sections</SelectItem>
                {sectionOptions.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {teacherOptions.length > 0 && (
            <Select
              value={classTeacherFilter}
              onValueChange={setClassTeacherFilter}
            >
              <SelectTrigger className="h-9 sm:w-48">
                <SelectValue placeholder="Class teacher" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All class teachers</SelectItem>
                {teacherOptions.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {(search ||
            classFilter !== ALL ||
            sectionFilter !== ALL ||
            classTeacherFilter !== ALL) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSearch("");
                setClassFilter(ALL);
                setSectionFilter(ALL);
                setClassTeacherFilter(ALL);
              }}
            >
              Clear
            </Button>
          )}
          <div className="sm:ml-auto">
            <ExportButton
              label="Export"
              loading={isLoading}
              disabled={initialSorted.length === 0}
              options={() => ({
                subject: "Students",
                schoolName: user?.school_name ?? null,
                filters: activeFilters,
                columns: exportColumns,
                rows: initialSorted,
              })}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <DataTable
            data={initialSorted}
            columns={columns}
            rowKey={(r) => r.id}
            loading={isLoading}
            onRowClick={(r) => setActiveId(r.id)}
            empty={
              <EmptyState
                compact
                icon={<UsersIcon className="h-5 w-5" />}
                title="No students match"
                description="Adjust the filters above or wait for the next sync from the ERP."
              />
            }
          />
        </CardContent>
      </Card>

      <Sheet
        open={!!activeId}
        onOpenChange={(open) => !open && setActiveId(null)}
      >
        <SheetContent description="Student profile, teachers, and 14-day activity timeline.">
          {activeId && <StudentSheet id={activeId} />}
        </SheetContent>
      </Sheet>
    </div>
  );
}

// ── Sheet content ─────────────────────────────────────────────────────

function StudentSheet({ id }: { id: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-student-detail", id],
    queryFn: () => api.adminStudentDetail(id),
  });

  if (isLoading) {
    return (
      <>
        <SheetHeader>
          <SheetTitle>Loading student…</SheetTitle>
        </SheetHeader>
        <SheetBody>
          <Skeleton className="h-24 w-full" />
          <Skeleton className="mt-3 h-48 w-full" />
        </SheetBody>
      </>
    );
  }
  if (!data) {
    return (
      <>
        <SheetHeader>
          <SheetTitle>Student</SheetTitle>
        </SheetHeader>
        <SheetBody>
          <EmptyState compact title="Couldn't load student" />
        </SheetBody>
      </>
    );
  }

  const s = data.student;
  const timeline = data.activity_timeline;
  const series = timeline.map((d) => d.count);
  const total = series.reduce((a, b) => a + b, 0);

  return (
    <>
      <SheetHeader>
        <SheetTitle>{s.full_name}</SheetTitle>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="truncate">{s.email}</span>
          {s.class_section && (
            <>
              <span>·</span>
              <Badge variant="secondary">{s.class_section}</Badge>
            </>
          )}
        </div>
      </SheetHeader>

      <SheetBody>
        {/* Class teacher */}
        <section>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Class teacher
          </h4>
          {data.class_teacher ? (
            <div className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm">
              {data.class_teacher.full_name}
            </div>
          ) : (
            <EmptyState
              compact
              title="No class teacher assigned"
              description="The ERP hasn't designated a class teacher for this section yet."
            />
          )}
        </section>

        {/* Subject teachers */}
        <section className="mt-5">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Subject teachers
          </h4>
          {data.subject_teachers.length === 0 ? (
            <EmptyState
              compact
              title="No subject teachers found"
              description="No teacher has this student's class in their assigned_classes list."
            />
          ) : (
            <ul className="space-y-1">
              {data.subject_teachers.map((t) => (
                <li
                  key={t.id}
                  className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm"
                >
                  <div>{t.full_name}</div>
                  {t.subjects.length > 0 && (
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      {t.subjects.join(", ")}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Activity timeline */}
        <section className="mt-5">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            AI activity · last 14 days
          </h4>
          {total === 0 ? (
            <EmptyState
              compact
              title="No AI activity in the last 14 days"
              description="This student hasn't used an AI feature recently."
            />
          ) : (
            <div className="rounded-md border border-border bg-surface-2 p-3">
              <div className="flex items-end justify-between gap-3">
                <div>
                  <div className="text-2xl font-bold tabular-nums">
                    {total.toLocaleString()}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    actions in 14 days
                  </div>
                </div>
                {series.length >= 2 && (
                  <Sparkline
                    data={series}
                    width={140}
                    height={32}
                    className="text-primary"
                  />
                )}
              </div>
            </div>
          )}
        </section>
      </SheetBody>
    </>
  );
}
