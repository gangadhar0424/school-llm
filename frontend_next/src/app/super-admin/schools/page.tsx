import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { SuperAdminSchoolsClient } from "./schools-client";

export const metadata = { title: "Schools · Super Admin" };

export default async function SuperAdminSchoolsPage() {
  await requireRole("super_admin");
  return (
    <>
      <DashboardHeader
        title="Schools"
        subtitle="Every tenant that has logged into the app"
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <SuperAdminSchoolsClient />
        </div>
      </main>
    </>
  );
}
