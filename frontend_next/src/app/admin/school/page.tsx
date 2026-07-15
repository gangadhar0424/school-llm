import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { AdminSchoolClient } from "./school-client";

export const metadata = { title: "School — Admin · School LLM" };

export default async function Page() {
  const user = await requireRole("admin");
  const subtitleParts = [];
  if (user.school_name) {
    subtitleParts.push(`Headcount and pulse for ${user.school_name}`);
  } else {
    subtitleParts.push("Headcount and pulse — your school at a glance");
  }
  if (user.school_plan) {
    subtitleParts.push(`Plan: ${user.school_plan}`);
  }
  const subtitle = `${subtitleParts.join(" · ")}.`;
  return (
    <>
      <DashboardHeader title="School" subtitle={subtitle} />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-5xl">
          <AdminSchoolClient />
        </div>
      </main>
    </>
  );
}
