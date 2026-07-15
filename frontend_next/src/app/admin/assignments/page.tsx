import { requireRole } from "@/lib/auth";
import { AdminAssignmentsClient } from "./assignments-client";
import { DashboardHeader } from "@/components/dashboard/header";

export const metadata = {
  title: "Assignments | Admin",
};

export default async function AdminAssignmentsPage() {
  const user = await requireRole("admin");
  return (
    <>
      <DashboardHeader
        title="Assignments"
        subtitle="Track assignments published by teachers in your school and see how many students have submitted them."
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <AdminAssignmentsClient />
        </div>
      </main>
    </>
  );
}
