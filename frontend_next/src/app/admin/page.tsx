import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { AdminAnalyticsClient } from "./analytics-client";

export const metadata = { title: "Admin · School LLM" };

export default async function AdminHomePage() {
  const user = await requireRole("admin");
  return (
    <>
      <DashboardHeader
        title="Analytics"
        subtitle="Users · activity · feature usage"
        schoolChip={user.school_name}
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-6xl">
          <AdminAnalyticsClient />
        </div>
      </main>
    </>
  );
}
