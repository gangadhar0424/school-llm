import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { SuperAdminOverviewClient } from "./overview-client";

export const metadata = { title: "Super Admin · School LLM" };

export default async function SuperAdminHomePage() {
  await requireRole("super_admin");
  return (
    <>
      <DashboardHeader
        title="Analytics"
        subtitle="Users · activity · feature usage (all schools)"
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <SuperAdminOverviewClient />
        </div>
      </main>
    </>
  );
}
