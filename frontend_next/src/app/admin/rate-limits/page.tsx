import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { AdminRateLimitsClient } from "./rate-limits-client";

export const metadata = { title: "Rate Limits — Admin · School LLM" };

export default async function Page() {
  await requireRole("admin");
  return (
    <>
      <DashboardHeader
        title="⏱️ Rate Limits"
        subtitle="Per-role daily quotas. -1 = unlimited · 0 = disabled."
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-5xl">
          <AdminRateLimitsClient />
        </div>
      </main>
    </>
  );
}
