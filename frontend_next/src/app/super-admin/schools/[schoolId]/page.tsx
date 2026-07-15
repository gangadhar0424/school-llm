import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { SuperAdminSchoolDetailClient } from "./school-detail-client";

export const metadata = { title: "School · Super Admin" };

export default async function SuperAdminSchoolDetailPage({
  params,
}: {
  params: Promise<{ schoolId: string }>;
}) {
  await requireRole("super_admin");
  const { schoolId } = await params;
  const sid = Number(schoolId);

  return (
    <>
      <DashboardHeader
        title={`School #${sid}`}
        subtitle="Users and rate limits"
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-6xl space-y-4">
          <Link
            href="/super-admin/schools"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to schools
          </Link>
          <SuperAdminSchoolDetailClient schoolId={sid} />
        </div>
      </main>
    </>
  );
}
