import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { SuperAdminDefaultLimitsClient } from "./default-limits-client";

export const metadata = { title: "Default limits · Super Admin" };

export default async function SuperAdminDefaultLimitsPage() {
  await requireRole("super_admin");
  return (
    <>
      <DashboardHeader
        title="Default rate limits"
        subtitle="Applied to any school without a per-school override"
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-4xl">
          <SuperAdminDefaultLimitsClient />
        </div>
      </main>
    </>
  );
}
