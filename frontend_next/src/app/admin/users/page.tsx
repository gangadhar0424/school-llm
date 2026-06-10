import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { AdminUsersClient } from "./users-client";

export const metadata = { title: "Users — Admin · School LLM" };

export default async function Page() {
  const user = await requireRole("admin");
  return (
    <>
      <DashboardHeader
        title="Users"
        subtitle="Activate accounts, edit class assignments, set teacher roles."
        schoolChip={user.school_name}
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <AdminUsersClient />
        </div>
      </main>
    </>
  );
}
