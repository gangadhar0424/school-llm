import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { TeacherUploadPdfTrigger } from "@/components/teacher/upload-pdf-trigger";
import { NewAssignmentClient } from "./new-assignment-client";

export const metadata = { title: "New Assignment — Teacher · School LLM" };

export default async function Page() {
  const user = await requireRole("teacher");
  return (
    <>
      <DashboardHeader title="➕ New Assignment">
        <TeacherUploadPdfTrigger />
      </DashboardHeader>
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-4xl">
          <NewAssignmentClient
            assignedClasses={user.assigned_classes}
            subjectsTaught={user.subjects_taught}
          />
        </div>
      </main>
    </>
  );
}
