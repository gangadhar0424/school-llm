"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DataTable,
  type DataTableColumn,
  type RowAction,
} from "@/components/ui/data-table";
import { UploadPdfDialog } from "@/components/dashboard/upload-pdf-dialog";
import { ExportButton } from "@/components/admin/export-button";
import { csvDate, type ExportColumn } from "@/lib/csv-export";
import { useCurrentUser } from "@/lib/use-current-user";
import { formatRelative } from "@/lib/utils";
import type { AdminPdfItem, Role } from "@/lib/types";

const ALL = "__all__";
type RoleFilter = typeof ALL | Role;

// Visual treatment for the role badge next to each uploader email.
// Mirrors the conventions used elsewhere in the admin (analytics tiles,
// activity feed) so the colour reads the same across pages.
const ROLE_BADGE: Record<Role, { variant: "secondary" | "outline"; label: string }> = {
  super_admin: { variant: "outline", label: "Super Admin" },
  admin: { variant: "outline", label: "Admin" },
  teacher: { variant: "secondary", label: "Teacher" },
  student: { variant: "outline", label: "Student" },
};

const PDFS_KEY = ["admin-pdfs"] as const;

export function AdminPdfsClient() {
  const user = useCurrentUser();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: PDFS_KEY,
    queryFn: () => api.adminGetUploadedPdfs(500),
  });
  const [search, setSearch] = React.useState("");
  const [roleFilter, setRoleFilter] = React.useState<RoleFilter>(ALL);

  const del = useMutation({
    mutationFn: (id: string) => api.deletePdf(id),
    onSuccess: () => {
      toast.success("PDF deleted.");
      qc.invalidateQueries({ queryKey: PDFS_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  // Stable reference for the useMemo + dropdown-visibility derivation
  // below — `data?.pdfs ?? []` creates a new array every render.
  const allRows = React.useMemo(() => data?.pdfs ?? [], [data]);

  // If no row carries an uploader_role (older backend, empty mirror,
  // local-mode), don't show the dropdown — the filter would be useless
  // and the "Unknown" bucket would dominate.
  const anyRoleKnown = allRows.some((p) => !!p.uploader_role);

  const rows = React.useMemo(() => {
    const q = search.trim().toLowerCase();
    return allRows.filter((p) => {
      if (q) {
        if (
          !`${p.filename ?? ""} ${p.uploader_email ?? ""}`
            .toLowerCase()
            .includes(q)
        ) {
          return false;
        }
      }
      if (roleFilter !== ALL && p.uploader_role !== roleFilter) return false;
      return true;
    });
  }, [allRows, search, roleFilter]);

  // Every getter below is defensive — old uploads predate some fields
  // and the admin endpoint returns the raw documents, missing fields and
  // all. Coalesce to safe defaults so a single bad row can't crash the
  // table.
  const columns: DataTableColumn<AdminPdfItem>[] = [
    {
      key: "filename",
      header: "Filename",
      sortable: true,
      sortValue: (p) => (p.filename || "").toLowerCase(),
      cell: (p) => (
        <div className="flex items-center gap-2.5">
          <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="truncate text-sm font-medium text-foreground">
            {p.filename || "(untitled)"}
          </span>
        </div>
      ),
    },
    {
      key: "uploader",
      header: "Uploaded by",
      sortable: true,
      sortValue: (p) => p.uploader_email || "",
      width: "w-64",
      cell: (p) => (
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="truncate text-xs text-muted-foreground">
            {p.uploader_email || "—"}
          </span>
          {p.uploader_role && (
            <Badge
              variant={ROLE_BADGE[p.uploader_role].variant}
              className="text-[10px]"
            >
              {ROLE_BADGE[p.uploader_role].label}
            </Badge>
          )}
        </div>
      ),
    },
    {
      key: "pages",
      header: "Pages",
      sortable: true,
      sortValue: (p) => (typeof p.total_pages === "number" ? p.total_pages : -1),
      width: "w-20",
      align: "right",
      cell: (p) => (
        <span className="text-xs tabular-nums text-muted-foreground">
          {typeof p.total_pages === "number"
            ? p.total_pages.toLocaleString()
            : "—"}
        </span>
      ),
    },
    {
      key: "size",
      header: "Size",
      sortable: true,
      sortValue: (p) => (typeof p.file_size === "number" ? p.file_size : -1),
      width: "w-24",
      align: "right",
      cell: (p) => (
        <span className="text-xs tabular-nums text-muted-foreground">
          {typeof p.file_size === "number" ? formatBytes(p.file_size) : "—"}
        </span>
      ),
    },
    {
      key: "uploaded",
      header: "Uploaded",
      sortable: true,
      sortValue: (p) =>
        p.uploaded_at ? new Date(p.uploaded_at).getTime() : 0,
      width: "w-32",
      align: "right",
      cell: (p) => (
        <span className="text-xs text-muted-foreground">
          {p.uploaded_at ? formatRelative(p.uploaded_at) : "—"}
        </span>
      ),
    },
  ];

  const rowActions = (p: AdminPdfItem): RowAction[] => [
    {
      label: "Delete",
      icon: Trash2,
      destructive: true,
      disabled: del.isPending,
      onClick: () => {
        if (confirm(`Delete "${p.filename}"? This cannot be undone.`)) {
          del.mutate(p.id);
        }
      },
    },
  ];

  const exportColumns: ExportColumn<AdminPdfItem>[] = React.useMemo(
    () => [
      { header: "Filename", value: (p) => p.filename ?? "" },
      { header: "Uploader email", value: (p) => p.uploader_email ?? "" },
      { header: "Uploader role", value: (p) => p.uploader_role ?? "" },
      { header: "Pages", value: (p) => p.total_pages ?? 0 },
      { header: "Size (bytes)", value: (p) => p.file_size ?? 0 },
      { header: "Uploaded at", value: (p) => csvDate(p.uploaded_at) },
    ],
    []
  );
  const activeFilters = React.useMemo(() => {
    const bits: string[] = [];
    if (search) bits.push(`search="${search}"`);
    if (roleFilter !== ALL) bits.push(`uploader_role=${roleFilter}`);
    return bits.length === 0 ? "none" : bits.join(", ");
  }, [search, roleFilter]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative max-w-sm flex-1">
            <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search filename or uploader…"
              className="h-9 pl-8"
            />
          </div>
          {anyRoleKnown && (
            <Select
              value={roleFilter}
              onValueChange={(v) => setRoleFilter(v as RoleFilter)}
            >
              <SelectTrigger className="h-9 sm:w-44">
                <SelectValue placeholder="Uploaded by" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All uploaders</SelectItem>
                <SelectItem value="teacher">Teachers</SelectItem>
                <SelectItem value="student">Students</SelectItem>
                <SelectItem value="admin">Admins</SelectItem>
              </SelectContent>
            </Select>
          )}
          {(search || roleFilter !== ALL) && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setSearch("");
                setRoleFilter(ALL);
              }}
            >
              Clear
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <ExportButton
            label="Export"
            loading={isLoading}
            disabled={rows.length === 0}
            options={() => ({
              subject: "PDFs",
              schoolName: user?.school_name ?? null,
              filters: activeFilters,
              columns: exportColumns,
              rows: rows,
            })}
          />
          <UploadPdfDialog
            triggerSize="sm"
            onUploaded={() => qc.invalidateQueries({ queryKey: PDFS_KEY })}
          />
        </div>
      </div>
      <DataTable<AdminPdfItem>
        data={rows}
        columns={columns}
        rowKey={(p) => p.id}
        loading={isLoading}
        pageSize={25}
        rowActions={rowActions}
        empty={
          <div className="flex flex-col items-center gap-2 py-6">
            <FileText className="h-6 w-6 text-muted-foreground" />
            <p className="text-sm font-medium">No PDFs</p>
            <p className="text-xs text-muted-foreground">
              {search ? "Try clearing your search." : "Nothing has been uploaded yet."}
            </p>
          </div>
        }
      />
    </div>
  );
}

function formatBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${(b / 1024 / 1024).toFixed(1)} MB`;
}
