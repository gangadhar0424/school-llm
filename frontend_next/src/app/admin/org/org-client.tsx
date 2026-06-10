"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Network } from "lucide-react";
import { api } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ExportButton } from "@/components/admin/export-button";
import { csvList, type ExportColumn } from "@/lib/csv-export";
import { useCurrentUser } from "@/lib/use-current-user";
import { cn } from "@/lib/utils";
import type {
  RelationshipsEdge,
  RelationshipsTeacher,
} from "@/lib/types";

// One row per (teacher, class, subjects) edge — what the CSV exports.
interface OrgChartRow {
  teacher_name: string;
  erp_title: string;
  class_section: string;
  subjects: string[];
}

type Mode = "by_class" | "by_teacher";

export function AdminOrgClient() {
  const user = useCurrentUser();
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-school-relationships"],
    queryFn: () => api.adminSchoolRelationships(),
    staleTime: 60_000,
  });

  const [mode, setMode] = React.useState<Mode>("by_class");
  const [selectedClass, setSelectedClass] = React.useState<string | null>(null);
  const [selectedTeacherId, setSelectedTeacherId] = React.useState<string | null>(null);

  // Default-select the first option in each mode as soon as data arrives.
  // React 19 forbids setState in effects, so we use the tracked-prop idiom.
  const [tracked, setTracked] = React.useState({
    classes: 0,
    teachers: 0,
    mode,
  });
  const nextTracked = {
    classes: data?.classes.length ?? 0,
    teachers: data?.teachers.length ?? 0,
    mode,
  };
  if (
    tracked.classes !== nextTracked.classes ||
    tracked.teachers !== nextTracked.teachers ||
    tracked.mode !== nextTracked.mode
  ) {
    setTracked(nextTracked);
    if (mode === "by_class" && data?.classes.length && !selectedClass) {
      setSelectedClass(data.classes[0]);
    }
    if (
      mode === "by_teacher" &&
      data?.teachers.length &&
      !selectedTeacherId
    ) {
      setSelectedTeacherId(data.teachers[0].id);
    }
  }

  if (error) {
    return (
      <Card>
        <CardContent className="p-6">
          <EmptyState
            icon={<Network className="h-5 w-5" />}
            title="Couldn't load the relationships"
            description={String((error as Error).message)}
          />
        </CardContent>
      </Card>
    );
  }

  const noData =
    !isLoading && data && data.teachers.length === 0 && data.classes.length === 0;
  if (noData) {
    return (
      <Card>
        <CardContent className="p-6">
          <EmptyState
            icon={<Network className="h-5 w-5" />}
            title="No relationships yet"
            description="No teachers have assigned_classes or subjects_taught populated. Once the ERP starts sending these fields and a teacher logs in, the graph will fill in."
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Mode toggle + picker */}
      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
          <div
            role="tablist"
            aria-label="View mode"
            className="inline-flex items-center rounded-md border border-border bg-surface p-0.5"
          >
            <button
              role="tab"
              aria-selected={mode === "by_class"}
              onClick={() => setMode("by_class")}
              className={cn(
                "rounded-sm px-3 py-1 text-xs font-medium transition-colors",
                mode === "by_class"
                  ? "bg-primary-chip text-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              By class
            </button>
            <button
              role="tab"
              aria-selected={mode === "by_teacher"}
              onClick={() => setMode("by_teacher")}
              className={cn(
                "rounded-sm px-3 py-1 text-xs font-medium transition-colors",
                mode === "by_teacher"
                  ? "bg-primary-chip text-primary"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              By teacher
            </button>
          </div>

          {mode === "by_class" ? (
            <Select
              value={selectedClass ?? ""}
              onValueChange={(v) => setSelectedClass(v || null)}
            >
              <SelectTrigger className="h-9 sm:w-48">
                <SelectValue placeholder="Pick a class" />
              </SelectTrigger>
              <SelectContent>
                {(data?.classes ?? []).map((c) => (
                  <SelectItem key={c} value={c}>
                    {c}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Select
              value={selectedTeacherId ?? ""}
              onValueChange={(v) => setSelectedTeacherId(v || null)}
            >
              <SelectTrigger className="h-9 sm:w-64">
                <SelectValue placeholder="Pick a teacher" />
              </SelectTrigger>
              <SelectContent>
                {(data?.teachers ?? []).map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.full_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
          <div className="sm:ml-auto">
            <ExportButton
              label="Export"
              loading={isLoading}
              disabled={!data || data.edges.length === 0}
              options={() => {
                const teachersById = new Map(
                  (data?.teachers ?? []).map((t) => [t.id, t])
                );
                const rows: OrgChartRow[] = (data?.edges ?? []).map((e) => {
                  const t = teachersById.get(e.teacher_id);
                  return {
                    teacher_name: t?.full_name ?? e.teacher_id,
                    erp_title: t?.erp_title ?? "",
                    class_section: e.class_section,
                    subjects: e.subjects,
                  };
                });
                const cols: ExportColumn<OrgChartRow>[] = [
                  { header: "Teacher", value: (r) => r.teacher_name },
                  { header: "ERP title", value: (r) => r.erp_title },
                  { header: "Class section", value: (r) => r.class_section },
                  { header: "Subjects", value: (r) => csvList(r.subjects) },
                ];
                return {
                  subject: "Org chart",
                  schoolName: user?.school_name ?? null,
                  columns: cols,
                  rows,
                };
              }}
            />
          </div>
        </CardContent>
      </Card>

      {/* Chart */}
      <Card>
        <CardContent className="p-5">
          {isLoading ? (
            <Skeleton className="h-72 w-full" />
          ) : mode === "by_class" ? (
            <ByClassChart
              classSection={selectedClass}
              teachers={data?.teachers ?? []}
              edges={data?.edges ?? []}
            />
          ) : (
            <ByTeacherChart
              teacherId={selectedTeacherId}
              teachers={data?.teachers ?? []}
              edges={data?.edges ?? []}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ─── By-class chart ───────────────────────────────────────────────────
// Class node in the centre, each teacher on a spoke around it. Subjects
// label the spoke. Hub-and-spoke layout, ~250 lines of SVG total.

function ByClassChart({
  classSection,
  teachers,
  edges,
}: {
  classSection: string | null;
  teachers: RelationshipsTeacher[];
  edges: RelationshipsEdge[];
}) {
  if (!classSection) {
    return (
      <EmptyState
        title="Pick a class above"
        description="Select a class from the dropdown to see the teachers connected to it."
      />
    );
  }
  const teachersById = new Map(teachers.map((t) => [t.id, t]));
  const relevantEdges = edges.filter((e) => e.class_section === classSection);
  const spokeTeachers = relevantEdges
    .map((e) => ({
      teacher: teachersById.get(e.teacher_id),
      subjects: e.subjects,
    }))
    .filter((x): x is { teacher: RelationshipsTeacher; subjects: string[] } =>
      Boolean(x.teacher)
    );

  if (spokeTeachers.length === 0) {
    return (
      <EmptyState
        title={`No teachers connected to ${classSection}`}
        description="No teacher in the ERP has this class section in their assigned_classes list."
      />
    );
  }

  return (
    <HubAndSpokes
      hubLabel={classSection}
      hubSub="class"
      spokes={spokeTeachers.map(({ teacher, subjects }) => ({
        id: teacher.id,
        title: teacher.full_name,
        subtitle:
          subjects.length > 0
            ? subjects.join(", ")
            : teacher.erp_title || "Teacher",
      }))}
    />
  );
}

// ─── By-teacher chart ────────────────────────────────────────────────
// Teacher at the centre, each class they touch as a spoke. Same layout
// component, different content.

function ByTeacherChart({
  teacherId,
  teachers,
  edges,
}: {
  teacherId: string | null;
  teachers: RelationshipsTeacher[];
  edges: RelationshipsEdge[];
}) {
  if (!teacherId) {
    return (
      <EmptyState
        title="Pick a teacher above"
        description="Select a teacher from the dropdown to see the classes they teach."
      />
    );
  }
  const teacher = teachers.find((t) => t.id === teacherId);
  if (!teacher) {
    return (
      <EmptyState
        title="Teacher not found"
        description="The selected teacher isn't in the relationships payload."
      />
    );
  }
  const relevantEdges = edges.filter((e) => e.teacher_id === teacherId);
  if (relevantEdges.length === 0) {
    return (
      <EmptyState
        title={`${teacher.full_name} has no classes`}
        description="This teacher's assigned_classes list is empty in the ERP mirror."
      />
    );
  }

  return (
    <HubAndSpokes
      hubLabel={teacher.full_name}
      hubSub={teacher.erp_title ?? "Teacher"}
      spokes={relevantEdges.map((e) => ({
        id: e.class_section,
        title: e.class_section,
        subtitle:
          e.subjects.length > 0 ? e.subjects.join(", ") : "class",
      }))}
    />
  );
}

// ─── Hub + spokes SVG ────────────────────────────────────────────────
// Single layout primitive used by both views. Places the hub in the
// centre and arranges N spokes around it on a circle. Tilts the spoke
// labels so they always sit just outside the spoke node, not on top.

interface Spoke {
  id: string;
  title: string;
  subtitle?: string;
}

function HubAndSpokes({
  hubLabel,
  hubSub,
  spokes,
}: {
  hubLabel: string;
  hubSub: string;
  spokes: Spoke[];
}) {
  const width = 760;
  const height = 360;
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.36;
  const hubR = 40;
  const spokeR = 28;

  const N = spokes.length;
  // Distribute spokes evenly on a circle, starting at the top (-90°).
  const angles = Array.from(
    { length: N },
    (_, i) => -Math.PI / 2 + (i * 2 * Math.PI) / N
  );

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        className="h-72 w-full text-foreground"
        aria-label={`Hub and spokes: ${hubLabel}`}
      >
        {/* Lines first so spokes draw on top */}
        {spokes.map((s, i) => {
          const x = cx + radius * Math.cos(angles[i]);
          const y = cy + radius * Math.sin(angles[i]);
          return (
            <line
              key={`l-${s.id}`}
              x1={cx}
              y1={cy}
              x2={x}
              y2={y}
              stroke="currentColor"
              strokeOpacity="0.18"
              strokeWidth={1.5}
            />
          );
        })}

        {/* Hub */}
        <g>
          <circle
            cx={cx}
            cy={cy}
            r={hubR}
            className="fill-primary-chip stroke-primary"
            strokeWidth={1.5}
          />
          <text
            x={cx}
            y={cy - 3}
            textAnchor="middle"
            className="fill-primary text-sm font-semibold"
          >
            {truncate(hubLabel, 14)}
          </text>
          <text
            x={cx}
            y={cy + 12}
            textAnchor="middle"
            className="fill-muted-foreground text-[10px] uppercase tracking-wider"
          >
            {hubSub}
          </text>
        </g>

        {/* Spokes */}
        {spokes.map((s, i) => {
          const x = cx + radius * Math.cos(angles[i]);
          const y = cy + radius * Math.sin(angles[i]);
          // Push labels outwards from the centre so they sit outside
          // the node, not on top of it. Anchor flips based on side.
          const labelDx = Math.cos(angles[i]) * (spokeR + 8);
          const labelDy = Math.sin(angles[i]) * (spokeR + 8);
          const labelAnchor =
            labelDx > 6 ? "start" : labelDx < -6 ? "end" : "middle";
          return (
            <g key={s.id}>
              <circle
                cx={x}
                cy={y}
                r={spokeR}
                className="fill-surface stroke-border"
                strokeWidth={1.5}
              />
              <text
                x={x}
                y={y + 4}
                textAnchor="middle"
                className="fill-foreground text-xs font-medium"
              >
                {truncate(s.title, 8)}
              </text>
              {s.subtitle && (
                <text
                  x={x + labelDx}
                  y={y + labelDy + 4}
                  textAnchor={labelAnchor}
                  className="fill-muted-foreground text-[10px]"
                >
                  {truncate(s.subtitle, 28)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function truncate(s: string, n: number) {
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}
