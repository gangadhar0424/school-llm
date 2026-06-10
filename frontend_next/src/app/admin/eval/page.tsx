import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { AdminEvalClient } from "./eval-client";
import { AnswerEvaluatorTrigger } from "@/components/admin/answer-evaluator-trigger";

export const metadata = { title: "AI Evaluation — Admin · School LLM" };

export default async function Page() {
  await requireRole("admin");
  return (
    <>
      <DashboardHeader title="🧪 AI Evaluation">
        <AnswerEvaluatorTrigger />
      </DashboardHeader>
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <AdminEvalClient />
        </div>
      </main>
    </>
  );
}
