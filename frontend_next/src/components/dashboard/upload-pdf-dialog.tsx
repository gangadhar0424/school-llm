"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Upload } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Button, type ButtonProps } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { USAGE_QUERY_KEY } from "@/components/dashboard/usage-card";

/**
 * Multi-file PDF upload, shared by the student Home page and the
 * /admin/pdfs page. Pops a small dialog, uploads sequentially with a
 * per-file progress line, fires `onUploaded` after the whole batch.
 *
 * The trigger is overridable so each consumer can match its own visual
 * style: students get a primary "Upload PDF" button; admins get an
 * outline-variant button next to the search input.
 */
export interface UploadPdfDialogProps {
  /** Fired once after every file has been processed (success or fail).
   *  Use it to invalidate React Query keys on the parent — neither the
   *  dialog nor api.uploadPdf does that for you. */
  onUploaded?: () => void;
  /** Customise the visual style of the trigger button. The label and
   *  icon stay the same. */
  triggerVariant?: ButtonProps["variant"];
  triggerSize?: ButtonProps["size"];
  /** Override the trigger label. Default "Upload PDF". */
  triggerLabel?: React.ReactNode;
}

export function UploadPdfDialog({
  onUploaded,
  triggerVariant = "default",
  triggerSize = "md",
  triggerLabel = "Upload PDF",
}: UploadPdfDialogProps) {
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
      // Usage invalidation is universal — every uploader has a quota.
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
    onUploaded?.();
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant={triggerVariant} size={triggerSize}>
          <Upload className="h-4 w-4" /> {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload a PDF</DialogTitle>
          <DialogDescription>
            Drop one or more PDFs. Each one is indexed for Q&amp;A and
            Workspace features.
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
