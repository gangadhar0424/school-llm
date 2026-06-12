"use client";

import * as React from "react";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { BookOpen, FileText, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Input } from "@/components/ui/input";
import {
  DataTable,
  type DataTableColumn,
  type RowAction,
} from "@/components/ui/data-table";
import { EmptyState } from "@/components/ui/empty-state";
import { formatRelative } from "@/lib/utils";
import type { PdfItem } from "@/lib/types";

const TEACHER_PDFS_KEY = ["teacher-pdfs"] as const;

export function TeacherPdfsClient() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: TEACHER_PDFS_KEY,
    queryFn: () => api.myPdfs(500),
  });
  const [search, setSearch] = React.useState("");

  const del = useMutation({
    mutationFn: (id: string) => api.deletePdf(id),
    onSuccess: () => {
      toast.success("PDF deleted.");
      qc.invalidateQueries({ queryKey: TEACHER_PDFS_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  const rows = React.useMemo(() => {
    const all = data?.pdfs ?? [];
    if (!search.trim()) return all;
    const q = search.toLowerCase();
    return all.filter((p) => (p.filename ?? "").toLowerCase().includes(q));
  }, [data, search]);

  const columns: DataTableColumn<PdfItem>[] = [
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
      key: "pages",
      header: "Pages",
      sortable: true,
      sortValue: (p) =>
        typeof p.total_pages === "number" ? p.total_pages : -1,
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
      sortValue: (p) =>
        typeof p.file_size === "number" ? p.file_size : -1,
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

  const rowActions = (p: PdfItem): RowAction[] => [
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

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search filename…"
            className="h-9 pl-8"
          />
        </div>
      </div>
      <DataTable<PdfItem>
        data={rows}
        columns={columns}
        rowKey={(p) => p.id}
        loading={isLoading}
        pageSize={25}
        rowActions={rowActions}
        empty={
          <EmptyState
            compact
            icon={<BookOpen className="h-5 w-5" />}
            title="No PDFs yet"
            description={
              search
                ? "Try clearing your search."
                : "Upload your first PDF using the button above. Once it's processed, you can use it to generate Q&A, summaries, quizzes, and assignments."
            }
          />
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
