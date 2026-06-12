import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { TeacherUploadPdfTrigger } from "@/components/teacher/upload-pdf-trigger";
import { TeacherHomeClient } from "./home-client";

export const metadata = { title: "Home — Teacher · School LLM" };

export default async function TeacherHomePage() {
  const user = await requireRole("teacher");
  const subjects = user.subjects_taught.length
    ? user.subjects_taught.join(", ")
    : "no subjects assigned";
  const classes = user.assigned_classes.length
    ? user.assigned_classes.join(", ")
    : "no classes assigned";
  return (
    <>
      <DashboardHeader
        title={`Welcome back, ${user.full_name || user.username} 👋`}
        subtitle={`${subjects} · Classes: ${classes}`}
      >
        <TeacherUploadPdfTrigger />
      </DashboardHeader>
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <TeacherHomeClient />
      </main>
    </>
  );
}
