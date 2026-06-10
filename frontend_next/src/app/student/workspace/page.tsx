import { requireRole } from "@/lib/auth";
import { DashboardHeader } from "@/components/dashboard/header";
import { WorkspaceClient } from "./workspace-client";

export const metadata = { title: "Workspace — Student · School LLM" };

interface PageProps {
  searchParams: Promise<{ pdf?: string; tab?: string }>;
}

export default async function StudentWorkspacePage({ searchParams }: PageProps) {
  await requireRole("student");
  const params = await searchParams;
  return (
    <>
      <DashboardHeader
        title="📚 Workspace"
        subtitle="Q&A · Multi-Doc · Quiz · Summary · Audio · Video"
      />
      <main className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <WorkspaceClient
          initialPdfId={params.pdf || null}
          initialTab={params.tab || "qa"}
        />
      </main>
    </>
  );
}
