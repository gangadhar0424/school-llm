import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { AdminPdfsClient } from "./pdfs-client";

export const metadata = { title: "All PDFs — Admin · School LLM" };

export default async function Page() {
  const user = await requireRole("admin");
  return (
    <>
      <DashboardHeader
        title="PDFs"
        subtitle="Every PDF uploaded across the platform."
        schoolChip={user.school_name}
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <AdminPdfsClient />
        </div>
      </main>
    </>
  );
}
