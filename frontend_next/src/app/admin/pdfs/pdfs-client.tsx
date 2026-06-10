"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelative } from "@/lib/utils";

const PDFS_KEY = ["admin-pdfs"] as const;

export function AdminPdfsClient() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: PDFS_KEY,
    queryFn: () => api.adminGetUploadedPdfs(200),
  });
  const del = useMutation({
    mutationFn: (id: string) => api.deletePdf(id),
    onSuccess: () => {
      toast.success("PDF deleted.");
      qc.invalidateQueries({ queryKey: PDFS_KEY });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });
  if (isLoading) return <Skeleton className="h-64 w-full" />;
  const items = data?.pdfs ?? [];
  if (items.length === 0)
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          No PDFs in the system.
        </CardContent>
      </Card>
    );
  return (
    <Card>
      <CardContent className="p-0">
        <ul className="divide-y divide-border">
          {items.map((p) => (
            <li
              key={p.id}
              className="flex items-center justify-between gap-3 px-4 py-3"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">📄 {p.filename}</p>
                <p className="text-xs text-muted-foreground">
                  by {p.uploader_email} · {p.total_pages} pages ·{" "}
                  {(p.file_size / 1024).toFixed(0)} KB · uploaded{" "}
                  {formatRelative(p.uploaded_at)}
                </p>
              </div>
              <Button
                size="sm"
                variant="ghost"
                className="text-danger hover:bg-danger/10"
                onClick={() => {
                  if (confirm(`Delete "${p.filename}"?`)) del.mutate(p.id);
                }}
                disabled={del.isPending}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
