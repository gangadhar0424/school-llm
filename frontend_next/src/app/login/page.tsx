import { redirect } from "next/navigation";
import Link from "next/link";
import { getCurrentUser, homeForRole } from "@/lib/auth";
import { LoginClient } from "./login-client";

export const metadata = {
  title: "Login — School LLM",
};

interface PageProps {
  searchParams: Promise<{ tab?: string; from?: string }>;
}

export default async function LoginPage({ searchParams }: PageProps) {
  const user = await getCurrentUser();
  if (user) redirect(homeForRole(user.role));

  const params = await searchParams;
  const initialTab = params.tab === "signup" ? "signup" : "login";

  return (
    <main className="flex flex-1 items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <div className="text-5xl">📚</div>
          <h1 className="mt-2 text-2xl font-semibold text-foreground">
            School LLM
          </h1>
          <p className="text-sm text-muted-foreground">
            AI-powered learning platform
          </p>
        </div>
        <LoginClient initialTab={initialTab} />
        <p className="mt-6 text-center text-xs">
          <Link href="/" className="text-muted-foreground hover:underline">
            ← Back to home
          </Link>
        </p>
      </div>
    </main>
  );
}
