import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { AdminPermissionsClient } from "./permissions-client";

export const metadata = { title: "Roles & Permissions — Admin · School LLM" };

export default async function Page() {
  await requireRole("admin");
  return (
    <>
      <DashboardHeader
        title="🔐 Roles & Permissions"
        subtitle="Toggle per-feature access for each role. Changes apply immediately."
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-5xl">
          <AdminPermissionsClient />
        </div>
      </main>
    </>
  );
}
