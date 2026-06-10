import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { AdminPdfsClient } from "./pdfs-client";

export const metadata = { title: "All PDFs — Admin · School LLM" };

export default async function Page() {
  await requireRole("admin");
  return (
    <>
      <DashboardHeader title="📄 All PDFs" />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <AdminPdfsClient />
        </div>
      </main>
    </>
  );
}
