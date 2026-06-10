import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { AdminTeachersClient } from "./teachers-client";

export const metadata = { title: "Teachers — Admin · School LLM" };

export default async function Page() {
  const user = await requireRole("admin");
  return (
    <>
      <DashboardHeader
        title="Teachers"
        subtitle="Your school's faculty with their classes, subjects, and AI usage."
        schoolChip={user.school_name}
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <AdminTeachersClient />
        </div>
      </main>
    </>
  );
}
