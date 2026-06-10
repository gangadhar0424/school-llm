"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import {
  GraduationCap,
  Search,
  Users as UsersIcon,
} from "lucide-react";
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
import { ErpTitleBadge } from "@/components/admin/erp-title-badge";
import { ExportButton } from "@/components/admin/export-button";
import { csvDate, csvList, type ExportColumn } from "@/lib/csv-export";
import { useCurrentUser } from "@/lib/use-current-user";
import { formatRelative } from "@/lib/utils";
import type { TeacherListRow } from "@/lib/types";

// Friendly labels for the AI activity types coming back from the backend.
// Anything we forget to label here falls back to the raw key (Title cased).
const FEATURE_LABELS: Record<string, string> = {
  qa: "Q&A",
  summary: "Summary",
  quiz: "Quiz",
  audio: "Audio",
  video: "Video",
  short_answer: "Short answer",
  long_answer: "Long answer",
  mcq: "MCQ",
  fill_in_blank: "Fill in blank",
  true_false: "True / False",
  question_paper: "Question paper",
};

const ALL = "__all__";

export function AdminTeachersClient() {
  const user = useCurrentUser();
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-teachers"],
    queryFn: () => api.adminListTeachers(),
    staleTime: 30_000,
  });

  const [search, setSearch] = React.useState("");
  const [titleFilter, setTitleFilter] = React.useState<string>(ALL);
  const [classFilter, setClassFilter] = React.useState<string>(ALL);
  const [subjectFilter, setSubjectFilter] = React.useState<string>(ALL);
  const [activeId, setActiveId] = React.useState<string | null>(null);

  // Stable reference for downstream useMemo — `data?.teachers ?? []`
  // creates a new array every render, defeating the memoization.
  const teachers = React.useMemo(() => data?.teachers ?? [], [data]);

  // Build the dropdown option lists from the data itself — empty filters
  // are hidden so a school with no recorded subjects doesn't see a
  // useless "Subject" dropdown.
  const { titleOptions, classOptions, subjectOptions } = React.useMemo(() => {
    const t = new Set<string>();
    const c = new Set<string>();
    const s = new Set<string>();
    for (const row of teachers) {
      if (row.erp_title) t.add(row.erp_title);
      row.assigned_classes.forEach((x) => c.add(x));
      row.subjects_taught.forEach((x) => s.add(x));
    }
    return {
      titleOptions: [...t].sort(),
      classOptions: [...c].sort(),
      subjectOptions: [...s].sort(),
    };
  }, [teachers]);

  const filtered = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    return teachers.filter((t) => {
      if (q && !`${t.full_name} ${t.email}`.toLowerCase().includes(q)) return false;
      if (titleFilter !== ALL && t.erp_title !== titleFilter) return false;
      if (classFilter !== ALL && !t.assigned_classes.includes(classFilter)) return false;
      if (subjectFilter !== ALL && !t.subjects_taught.includes(subjectFilter)) return false;
      return true;
    });
  }, [teachers, search, titleFilter, classFilter, subjectFilter]);

  // 7.2 — hide columns whose data is empty for every row. The Subjects
  // column is the most common offender today (the ERP doesn't send the
  // field yet for most accounts).
  const showClassesCol = filtered.some((r) => r.assigned_classes.length > 0)
    || teachers.some((r) => r.assigned_classes.length > 0);
  const showSubjectsCol = filtered.some((r) => r.subjects_taught.length > 0)
    || teachers.some((r) => r.subjects_taught.length > 0);
  const showErpTitleCol = teachers.some((r) => !!r.erp_title);

  const columns: DataTableColumn<TeacherListRow>[] = [
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
    ...(showErpTitleCol
      ? [{
          key: "erp_title",
          header: "ERP title",
          sortable: true,
          sortValue: (r: TeacherListRow) => r.erp_title ?? "",
          width: "w-44",
          cell: (r: TeacherListRow) => <ErpTitleBadge title={r.erp_title} />,
        }]
      : []),
    ...(showClassesCol
      ? [{
          key: "classes",
          header: "Classes",
          width: "w-48",
          cell: (r: TeacherListRow) =>
            r.assigned_classes.length === 0 ? (
              <span className="text-xs text-muted-foreground">—</span>
            ) : (
              <div className="flex flex-wrap gap-1">
                {r.assigned_classes.map((c) => (
                  <Badge key={c} variant="secondary" className="text-[10px]">
                    {c}
                  </Badge>
                ))}
              </div>
            ),
        }]
      : []),
    ...(showSubjectsCol
      ? [{
          key: "subjects",
          header: "Subjects",
          width: "w-56",
          cell: (r: TeacherListRow) =>
            r.subjects_taught.length === 0 ? (
              <span className="text-xs text-muted-foreground">—</span>
            ) : (
              <span className="text-xs">{r.subjects_taught.join(", ")}</span>
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
      // Sort by ISO string descending = most recent first. Empty → bottom.
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

  // Initial sort: most recently active first. DataTable doesn't accept
  // a default sort prop, so we pre-sort the data here.
  const initialSorted = React.useMemo(() => {
    return [...filtered].sort((a, b) =>
      (b.last_active ?? "").localeCompare(a.last_active ?? "")
    );
  }, [filtered]);

  // Export columns mirror the visible table but with human-readable
  // headers and CSV-friendly cell formatters (joined lists, formatted
  // dates). Order matters — most-identifying columns first so an admin
  // can skim the file in Excel.
  const exportColumns: ExportColumn<TeacherListRow>[] = React.useMemo(
    () => [
      { header: "Name", value: (r) => r.full_name },
      { header: "Email", value: (r) => r.email },
      { header: "ERP title", value: (r) => r.erp_title ?? "" },
      { header: "Classes", value: (r) => csvList(r.assigned_classes) },
      { header: "Subjects", value: (r) => csvList(r.subjects_taught) },
      { header: "AI sessions (30 days)", value: (r) => r.ai_sessions_30d },
      { header: "Last active", value: (r) => csvDate(r.last_active) },
    ],
    []
  );

  const activeFilters = React.useMemo(() => {
    const bits: string[] = [];
    if (search) bits.push(`search="${search}"`);
    if (titleFilter !== ALL) bits.push(`title=${titleFilter}`);
    if (classFilter !== ALL) bits.push(`class=${classFilter}`);
    if (subjectFilter !== ALL) bits.push(`subject=${subjectFilter}`);
    return bits.length === 0 ? "none" : bits.join(", ");
  }, [search, titleFilter, classFilter, subjectFilter]);

  if (error) {
    return (
      <Card>
        <CardContent className="p-6">
          <EmptyState
            icon={<GraduationCap className="h-5 w-5" />}
            title="Couldn't load the teachers list"
            description={String((error as Error).message)}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Filter bar */}
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
          {titleOptions.length > 0 && (
            <Select value={titleFilter} onValueChange={setTitleFilter}>
              <SelectTrigger className="h-9 sm:w-44">
                <SelectValue placeholder="ERP title" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All titles</SelectItem>
                {titleOptions.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
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
          {subjectOptions.length > 0 && (
            <Select value={subjectFilter} onValueChange={setSubjectFilter}>
              <SelectTrigger className="h-9 sm:w-40">
                <SelectValue placeholder="Subject" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All subjects</SelectItem>
                {subjectOptions.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          {(search ||
            titleFilter !== ALL ||
            classFilter !== ALL ||
            subjectFilter !== ALL) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSearch("");
                setTitleFilter(ALL);
                setClassFilter(ALL);
                setSubjectFilter(ALL);
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
                subject: "Teachers",
                schoolName: user?.school_name ?? null,
                filters: activeFilters,
                columns: exportColumns,
                rows: initialSorted,
              })}
            />
          </div>
        </CardContent>
      </Card>

      {/* Table */}
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
                title="No teachers match"
                description="Adjust the filters above or wait for the next sync from the ERP."
              />
            }
          />
        </CardContent>
      </Card>

      {/* Drilldown sheet */}
      <Sheet
        open={!!activeId}
        onOpenChange={(open) => !open && setActiveId(null)}
      >
        <SheetContent description="Teacher profile, student roster, and 30-day AI activity.">
          {activeId && <TeacherSheet id={activeId} />}
        </SheetContent>
      </Sheet>
    </div>
  );
}

// ── Sheet content ─────────────────────────────────────────────────────

function TeacherSheet({ id }: { id: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-teacher-detail", id],
    queryFn: () => api.adminTeacherDetail(id),
  });

  if (isLoading) {
    return (
      <>
        <SheetHeader>
          <SheetTitle>Loading teacher…</SheetTitle>
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
          <SheetTitle>Teacher</SheetTitle>
        </SheetHeader>
        <SheetBody>
          <EmptyState compact title="Couldn't load teacher" />
        </SheetBody>
      </>
    );
  }

  const t = data.teacher;
  const usageEntries = Object.entries(data.ai_usage).sort(
    (a, b) => b[1] - a[1]
  );
  const usageTotal = usageEntries.reduce((s, [, v]) => s + v, 0);
  const usageMax = usageEntries[0]?.[1] ?? 0;

  return (
    <>
      <SheetHeader>
        <SheetTitle>{t.full_name}</SheetTitle>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="truncate">{t.email}</span>
          {t.erp_title && (
            <>
              <span>·</span>
              <ErpTitleBadge title={t.erp_title} />
            </>
          )}
        </div>
        {(t.assigned_classes.length > 0 || t.subjects_taught.length > 0) && (
          <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
            {t.assigned_classes.length > 0 && (
              <div>
                <div className="mb-1 text-muted-foreground">Classes</div>
                <div className="flex flex-wrap gap-1">
                  {t.assigned_classes.map((c) => (
                    <Badge key={c} variant="secondary">
                      {c}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            {t.subjects_taught.length > 0 && (
              <div>
                <div className="mb-1 text-muted-foreground">Subjects</div>
                <div>{t.subjects_taught.join(", ")}</div>
              </div>
            )}
          </div>
        )}
      </SheetHeader>

      <SheetBody>
        {/* Roster */}
        <section>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Their students ({data.roster.length})
          </h4>
          {data.roster.length === 0 ? (
            <EmptyState
              compact
              title="No students assigned"
              description="This teacher has no classes assigned yet, or no students have been mirrored from the ERP."
            />
          ) : (
            <ul className="max-h-48 space-y-1 overflow-y-auto rounded-md border border-border bg-surface-2 p-2">
              {data.roster.map((s) => (
                <li
                  key={s.id}
                  className="flex items-center justify-between gap-2 px-2 py-1 text-sm"
                >
                  <span className="truncate">{s.full_name}</span>
                  {s.class_section && (
                    <Badge variant="outline" className="text-[10px]">
                      {s.class_section}
                    </Badge>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* AI usage */}
        <section className="mt-5">
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            AI activity · last 30 days
          </h4>
          {usageTotal === 0 ? (
            <EmptyState
              compact
              title="No AI activity in the last 30 days"
              description="Either the teacher hasn't used an AI feature recently, or no activity has been logged for them yet."
            />
          ) : (
            <ul className="space-y-1.5">
              {usageEntries
                .filter(([, v]) => v > 0)
                .map(([k, v]) => (
                  <li key={k} className="text-xs">
                    <div className="mb-0.5 flex items-center justify-between">
                      <span>{FEATURE_LABELS[k] ?? k}</span>
                      <span className="tabular-nums text-muted-foreground">
                        {v.toLocaleString()}
                      </span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded bg-muted">
                      <div
                        className="h-full bg-primary"
                        style={{
                          width: `${usageMax > 0 ? (v / usageMax) * 100 : 0}%`,
                        }}
                      />
                    </div>
                  </li>
                ))}
            </ul>
          )}
        </section>
      </SheetBody>
    </>
  );
}
