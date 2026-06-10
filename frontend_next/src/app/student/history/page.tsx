import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { HistoryClient } from "./history-client";

export const metadata = { title: "History — Student · School LLM" };

export default async function StudentHistoryPage() {
  await requireRole("student");
  return (
    <>
      <DashboardHeader
        title="🕐 History"
        subtitle="Past Q&A, quizzes, summaries, audio, and videos."
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-5xl">
          <HistoryClient />
        </div>
      </main>
    </>
  );
}
