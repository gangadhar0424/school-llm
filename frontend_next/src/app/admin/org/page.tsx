import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { AdminOrgClient } from "./org-client";

export const metadata = { title: "Org chart — Admin · School LLM" };

export default async function Page() {
  const user = await requireRole("admin");
  return (
    <>
      <DashboardHeader
        title="Org chart"
        subtitle="Who teaches whom — pick a class or a teacher to see the relationships."
        schoolChip={user.school_name}
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-5xl">
          <AdminOrgClient />
        </div>
      </main>
    </>
  );
}
