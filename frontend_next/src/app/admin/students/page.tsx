import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { AdminStudentsClient } from "./students-client";

export const metadata = { title: "Students — Admin · School LLM" };

export default async function Page() {
  const user = await requireRole("admin");
  return (
    <>
      <DashboardHeader
        title="Students"
        subtitle="Every student in your school, grouped by class and section."
        schoolChip={user.school_name}
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <AdminStudentsClient />
        </div>
      </main>
    </>
  );
}
