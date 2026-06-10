import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { TeacherStudentsClient } from "./students-client";

export const metadata = { title: "My Students — Teacher · School LLM" };

export default async function Page() {
  await requireRole("teacher");
  return (
    <>
      <DashboardHeader title="👨‍🎓 My Students" />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-5xl">
          <TeacherStudentsClient />
        </div>
      </main>
    </>
  );
}
