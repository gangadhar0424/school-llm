import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { TeacherUploadPdfTrigger } from "@/components/teacher/upload-pdf-trigger";
import { TeacherAssignmentsList } from "./assignments-list";

export const metadata = { title: "My Assignments — Teacher · School LLM" };

export default async function TeacherAssignmentsPage() {
  await requireRole("teacher");
  return (
    <>
      <DashboardHeader title="📋 My Assignments">
        <TeacherUploadPdfTrigger />
      </DashboardHeader>
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-5xl">
          <TeacherAssignmentsList />
        </div>
      </main>
    </>
  );
}
