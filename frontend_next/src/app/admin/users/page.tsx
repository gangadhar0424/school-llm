import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { AdminUsersClient } from "./users-client";

export const metadata = { title: "Users — Admin · School LLM" };

export default async function Page() {
  await requireRole("admin");
  return (
    <>
      <DashboardHeader title="👥 Users" />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <AdminUsersClient />
        </div>
      </main>
    </>
  );
}
