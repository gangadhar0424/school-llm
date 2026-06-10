import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { AssignmentDetailClient } from "./assignment-detail-client";

interface PageProps {
  params: Promise<{ id: string }>;
}

export const metadata = { title: "Assignment — School LLM" };

export default async function AssignmentDetailPage({ params }: PageProps) {
  await requireRole("student");
  const { id } = await params;

  return (
    <>
      <DashboardHeader title="Assignment">
        <Button asChild variant="ghost" size="sm">
          <Link href="/student/assignments">
            <ArrowLeft className="h-4 w-4" /> All assignments
          </Link>
        </Button>
      </DashboardHeader>
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto max-w-3xl">
          <AssignmentDetailClient assignmentId={id} />
        </div>
      </main>
    </>
  );
}
