import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TeacherUploadPdfTrigger } from "@/components/teacher/upload-pdf-trigger";
import { TeacherAssignmentDetail } from "./detail-client";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function Page({ params }: PageProps) {
  await requireRole("teacher");
  const { id } = await params;
  return (
    <>
      <DashboardHeader title="Assignment">
        <Button asChild variant="ghost" size="sm">
          <Link href="/teacher/assignments">
            <ArrowLeft className="h-4 w-4" /> All assignments
          </Link>
        </Button>
        <TeacherUploadPdfTrigger />
      </DashboardHeader>
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-5xl">
          <TeacherAssignmentDetail assignmentId={id} />
        </div>
      </main>
    </>
  );
}
