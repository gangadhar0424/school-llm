import { redirect } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { getCurrentUser, homeForRole } from "@/lib/auth";

const FEATURES = [
  { icon: "💬", label: "Smart Q&A" },
  { icon: "📝", label: "Quiz Generator" },
  { icon: "📋", label: "Summaries" },
  { icon: "🔊", label: "Audio & Video" },
];

export default async function Home() {
  const user = await getCurrentUser();
  if (user) redirect(homeForRole(user.role));

  return (
    <main className="flex flex-1 items-center justify-center px-4 py-16">
      <div className="w-full max-w-2xl text-center">
        <div className="mb-2 text-6xl">📚</div>
        <h1 className="text-4xl font-bold tracking-tight text-foreground">
          School LLM
        </h1>
        <p className="mt-3 text-base text-muted-foreground">
          AI-powered learning platform — RAG · Quiz · Summary · Audio
        </p>

        <div className="mt-10 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {FEATURES.map((f) => (
            <div
              key={f.label}
              className="rounded-xl border border-border bg-surface px-3 py-4"
            >
              <div className="text-2xl">{f.icon}</div>
              <div className="mt-2 text-xs text-muted-foreground">
                {f.label}
              </div>
            </div>
          ))}
        </div>

        <div className="mx-auto mt-10 flex max-w-sm flex-col gap-3">
          <Button asChild size="lg">
            <Link href="/login">🔑 Login to your account</Link>
          </Button>
          <Button asChild variant="outline" size="lg">
            <Link href="/login?tab=signup">📝 Create a new account</Link>
          </Button>
        </div>

        <p className="mt-12 text-xs text-muted-foreground">
          Powered by Ollama · ChromaDB · FastAPI · MongoDB
        </p>
      </div>
    </main>
  );
}
