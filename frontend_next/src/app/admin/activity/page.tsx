import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { AdminActivityClient } from "./activity-client";

export const metadata = { title: "Activity — Admin · School LLM" };

export default async function Page() {
  const user = await requireRole("admin");
  return (
    <>
      <DashboardHeader
        title="Activity"
        subtitle="Audit trail of every user action across the platform."
        schoolChip={user.school_name}
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <AdminActivityClient />
        </div>
      </main>
    </>
  );
}
