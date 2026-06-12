import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { TeacherUploadPdfTrigger } from "@/components/teacher/upload-pdf-trigger";
import { TeacherPdfsClient } from "./pdfs-client";

export const metadata = { title: "My PDFs — Teacher · School LLM" };

export default async function Page() {
  await requireRole("teacher");
  return (
    <>
      <DashboardHeader
        title="My PDFs"
        subtitle="Every PDF you've uploaded — pick one to build an assignment from, or upload a new one."
      >
        <TeacherUploadPdfTrigger />
      </DashboardHeader>
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-5xl">
          <TeacherPdfsClient />
        </div>
      </main>
    </>
  );
}
