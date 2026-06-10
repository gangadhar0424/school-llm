"use client";

import * as React from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  KeyRound,
  Loader2,
  MessageSquare,
  Sparkles,
  Trash2,
  Upload,
  Flame,
  ListTodo,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { UsageCard, USAGE_QUERY_KEY } from "@/components/dashboard/usage-card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { formatRelative } from "@/lib/utils";
import type { PdfItem } from "@/lib/types";

const PDFS_KEY = ["my-pdfs"] as const;
const PROGRESS_KEY = ["student-progress"] as const;

export function StudentHomeClient() {
  const qc = useQueryClient();

  const { data: pdfsData, isLoading: pdfsLoading } = useQuery({
    queryKey: PDFS_KEY,
    queryFn: () => api.myPdfs(100),
  });
  const { data: progress } = useQuery({
    queryKey: PROGRESS_KEY,
    queryFn: api.studentProgress,
  });

  const pdfs = pdfsData?.pdfs ?? [];

  const onUploaded = () => {
    qc.invalidateQueries({ queryKey: PDFS_KEY });
    qc.invalidateQueries({ queryKey: PROGRESS_KEY });
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      {/* Hero with progress chips */}
      <div className="hero-grad rounded-2xl border border-border p-6">
        <div className="flex flex-wrap items-center gap-3">
          <Badge variant="soft" className="gap-1 text-xs">
            <Flame className="h-3 w-3" />
            {progress?.streak_days ?? 0}-day streak
          </Badge>
          <Badge variant="soft" className="gap-1 text-xs">
            <ListTodo className="h-3 w-3" />
            {progress?.pending_assignments ?? 0} pending assignments
          </Badge>
          <Badge variant="outline" className="gap-1 text-xs">
            <Sparkles className="h-3 w-3" />
            {progress?.features_used?.length ?? 0} of{" "}
            {progress?.total_features ?? "—"} features used
          </Badge>
        </div>
        <p className="mt-3 text-sm text-muted-foreground">
          Upload a PDF, open it in the Workspace, and let AI help you learn
          faster. Quotas reset daily.
        </p>
      </div>

      {/* Usage */}
      <UsageCard />

      {/* Actions row */}
      <div className="flex flex-wrap gap-3">
        <UploadPdfDialog onUploaded={onUploaded} />
        <ChangePasswordDialog />
      </div>

      {/* PDF library */}
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">📚 Your PDFs</h2>
          <p className="text-xs text-muted-foreground">
            {pdfs.length} total
          </p>
        </div>
        {pdfsLoading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : pdfs.length === 0 ? (
          <EmptyPdfState />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {pdfs.map((p) => (
              <PdfCard
                key={p.id}
                pdf={p}
                onDeleted={() => {
                  qc.invalidateQueries({ queryKey: PDFS_KEY });
                  qc.invalidateQueries({ queryKey: PROGRESS_KEY });
                }}
              />
            ))}
          </div>
        )}
      </section>

      {/* Recent activity */}
      {progress?.recent_pdfs && progress.recent_pdfs.length > 0 && (
        <section>
          <h2 className="mb-3 text-base font-semibold">🕐 Recent activity</h2>
          <Card>
            <CardContent className="p-0">
              <ul className="divide-y divide-border">
                {progress.recent_pdfs.slice(0, 5).map((p) => (
                  <li
                    key={p.id}
                    className="flex items-center justify-between gap-3 px-4 py-3"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">
                        📄 {p.filename}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {p.last_action || "uploaded"} ·{" "}
                        {formatRelative(p.last_action_at || p.uploaded_at)}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </section>
      )}
    </div>
  );
}

// ── PDF card ─────────────────────────────────────────────────────────────

function PdfCard({
  pdf,
  onDeleted,
}: {
  pdf: PdfItem;
  onDeleted: () => void;
}) {
  const del = useMutation({
    mutationFn: () => api.deletePdf(pdf.id),
    onSuccess: () => {
      toast.success(`Deleted ${pdf.filename}`);
      onDeleted();
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  return (
    <Card className="flex h-full flex-col">
      <CardContent className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-start gap-3">
          <div className="text-2xl">📄</div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-semibold" title={pdf.filename}>
              {pdf.filename}
            </div>
            <div className="text-xs text-muted-foreground">
              {pdf.total_pages} pages · uploaded {formatRelative(pdf.uploaded_at)}
            </div>
            {pdf.last_action && (
              <div className="mt-1 text-xs text-muted-foreground">
                Last used: <strong>{pdf.last_action}</strong>{" "}
                {pdf.last_action_at ? formatRelative(pdf.last_action_at) : ""}
              </div>
            )}
          </div>
        </div>
        <div className="mt-auto grid grid-cols-2 gap-2">
          <Button
            asChild
            variant="secondary"
            size="sm"
            className="justify-center"
          >
            <Link href={`/student/workspace?pdf=${pdf.pdf_identifier}&tab=qa`}>
              <MessageSquare className="h-3.5 w-3.5" />
              Q&A
            </Link>
          </Button>
          <Button
            asChild
            variant="secondary"
            size="sm"
            className="justify-center"
          >
            <Link
              href={`/student/workspace?pdf=${pdf.pdf_identifier}&tab=quiz`}
            >
              <Sparkles className="h-3.5 w-3.5" />
              Quiz
            </Link>
          </Button>
          <Button
            asChild
            variant="secondary"
            size="sm"
            className="col-span-2 justify-center"
          >
            <Link
              href={`/student/workspace?pdf=${pdf.pdf_identifier}&tab=summary`}
            >
              <FileText className="h-3.5 w-3.5" />
              Summary
            </Link>
          </Button>
          <Button
            variant="ghost"
            size="sm"
            disabled={del.isPending}
            onClick={() => {
              if (
                confirm(
                  `Delete "${pdf.filename}"? This removes all summaries, quizzes, and chat sessions tied to it.`
                )
              ) {
                del.mutate();
              }
            }}
            className="col-span-2 justify-center text-danger hover:bg-danger/10"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function EmptyPdfState() {
  return (
    <Card>
      <CardContent className="flex flex-col items-center gap-3 py-10 text-center">
        <div className="text-4xl">📤</div>
        <p className="text-sm font-medium">No PDFs yet</p>
        <p className="max-w-md text-xs text-muted-foreground">
          Upload your first textbook, lecture, or notes to unlock Q&A, quizzes,
          summaries, audio narration, and explainer videos.
        </p>
      </CardContent>
    </Card>
  );
}

// ── Upload dialog ────────────────────────────────────────────────────────

function UploadPdfDialog({ onUploaded }: { onUploaded: () => void }) {
  const [open, setOpen] = React.useState(false);
  const [files, setFiles] = React.useState<File[]>([]);
  const [progress, setProgress] = React.useState<{
    idx: number;
    name: string;
  } | null>(null);
  const qc = useQueryClient();

  const upload = useMutation({
    mutationFn: api.uploadPdf,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: USAGE_QUERY_KEY });
    },
  });

  const start = async () => {
    if (files.length === 0) return;
    for (let i = 0; i < files.length; i++) {
      setProgress({ idx: i + 1, name: files[i].name });
      try {
        const result = await upload.mutateAsync(files[i]);
        toast.success(`Uploaded ${result.filename}`);
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : "Upload failed";
        toast.error(`${files[i].name}: ${msg}`);
      }
    }
    setProgress(null);
    setFiles([]);
    setOpen(false);
    onUploaded();
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="default" size="md">
          <Upload className="h-4 w-4" /> Upload PDF
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>📤 Upload a PDF</DialogTitle>
          <DialogDescription>
            Drop one or more PDFs. Each one is indexed for Q&A and Workspace
            features.
          </DialogDescription>
        </DialogHeader>
        <Input
          type="file"
          accept="application/pdf"
          multiple
          onChange={(e) => setFiles(Array.from(e.target.files || []))}
        />
        {files.length > 0 && (
          <ul className="rounded-md border border-border bg-surface-2 p-2 text-xs">
            {files.map((f) => (
              <li key={f.name} className="truncate">
                · {f.name} ({Math.round(f.size / 1024)} KB)
              </li>
            ))}
          </ul>
        )}
        {progress && (
          <p className="text-xs text-muted-foreground">
            Uploading {progress.idx}/{files.length}: {progress.name}…
          </p>
        )}
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline" disabled={upload.isPending}>
              Cancel
            </Button>
          </DialogClose>
          <Button
            onClick={start}
            disabled={files.length === 0 || upload.isPending}
          >
            {upload.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Uploading…
              </>
            ) : (
              <>
                <Upload className="h-4 w-4" />
                Upload {files.length || ""}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Change-password dialog ───────────────────────────────────────────────

function ChangePasswordDialog() {
  const [open, setOpen] = React.useState(false);
  const [oldPw, setOldPw] = React.useState("");
  const [newPw, setNewPw] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [err, setErr] = React.useState<string | null>(null);

  const change = useMutation({
    mutationFn: () => api.changePassword(oldPw, newPw),
    onSuccess: () => {
      toast.success("Password changed.");
      setOldPw("");
      setNewPw("");
      setConfirm("");
      setOpen(false);
    },
    onError: (e: ApiError) => setErr(e.message),
  });

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    if (!oldPw || !newPw) return setErr("Fill in all fields.");
    if (newPw !== confirm) return setErr("New passwords do not match.");
    if (newPw.length < 8)
      return setErr("New password must be at least 8 characters.");
    change.mutate();
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline" size="md">
          <KeyRound className="h-4 w-4" /> Change Password
        </Button>
      </DialogTrigger>
      <DialogContent description="Update your account password. The new one must be at least 8 characters.">
        <DialogHeader>
          <DialogTitle>🔑 Change Password</DialogTitle>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-3">
          <div>
            <Label htmlFor="oldpw">Current password</Label>
            <Input
              id="oldpw"
              type="password"
              value={oldPw}
              onChange={(e) => setOldPw(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          <div>
            <Label htmlFor="newpw">New password</Label>
            <Input
              id="newpw"
              type="password"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              autoComplete="new-password"
              required
            />
          </div>
          <div>
            <Label htmlFor="confirmpw">Confirm new password</Label>
            <Input
              id="confirmpw"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              autoComplete="new-password"
              required
            />
          </div>
          {err && (
            <p className="rounded-md border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
              {err}
            </p>
          )}
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={change.isPending}>
              {change.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Saving…
                </>
              ) : (
                "Save"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
