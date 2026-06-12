"use client";

import { useQueryClient } from "@tanstack/react-query";
import { UploadPdfDialog } from "@/components/dashboard/upload-pdf-dialog";

/**
 * Header-mounted Upload PDF trigger for the teacher dashboard.
 *
 * Wraps the shared `UploadPdfDialog` with the teacher-specific query
 * invalidation: after a successful upload we refresh the My PDFs list
 * AND every cached teacher analytics period, so the PDF count tile and
 * recent-uploads list reflect the new file without a page reload.
 *
 * Lives in its own client file so the `teacher/page.tsx` Server
 * Component can drop it into the `DashboardHeader` children slot —
 * Next.js handles the server-to-client boundary automatically.
 */
export function TeacherUploadPdfTrigger() {
  const qc = useQueryClient();
  return (
    <UploadPdfDialog
      triggerLabel="Upload PDF"
      triggerVariant="outline"
      triggerSize="sm"
      onUploaded={() => {
        qc.invalidateQueries({ queryKey: ["teacher-pdfs"] });
        // The analytics query key is `["teacher-analytics", period]` —
        // invalidating the prefix refreshes every cached period at once.
        qc.invalidateQueries({ queryKey: ["teacher-analytics"] });
        qc.invalidateQueries({ queryKey: ["my-rate-limits"] });
      }}
    />
  );
}
