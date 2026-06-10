import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { ExportClient } from "./export-client";

export const metadata = { title: "Export — Admin · School LLM" };

export default async function Page() {
  await requireRole("admin");
  return (
    <>
      <DashboardHeader title="📥 Export logs" />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-2xl">
          <ExportClient />
        </div>
      </main>
    </>
  );
}
