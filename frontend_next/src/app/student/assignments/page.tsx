import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { AssignmentsList } from "./assignments-list";

export const metadata = { title: "Assignments — Student · School LLM" };

export default async function StudentAssignmentsPage() {
  await requireRole("student");
  return (
    <>
      <DashboardHeader
        title="📋 Assignments"
        subtitle="Your assignments. Tap one to attempt it. AI features are disabled inside an assignment."
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-4xl">
          <AssignmentsList />
        </div>
      </main>
    </>
  );
}
