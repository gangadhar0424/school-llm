import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { StudentHomeClient } from "./home-client";

export const metadata = { title: "Home — Student · School LLM" };

export default async function StudentHomePage() {
  const user = await requireRole("student");
  const classSection =
    user.class_level && user.section
      ? `${user.class_level}${user.section}`
      : "—";

  return (
    <>
      <DashboardHeader
        title={`Welcome back, ${user.full_name || user.username} 👋`}
        subtitle={`Class ${classSection}`}
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <StudentHomeClient />
      </main>
    </>
  );
}
