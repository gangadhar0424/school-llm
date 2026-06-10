import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";
import { getCurrentUser } from "@/lib/auth";
import { DEFAULT_THEME, isValidTheme, type ThemeName } from "@/lib/themes";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "School LLM",
  description: "AI-powered learning platform — RAG · Quiz · Summary · Audio",
};

export default async function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  // Read the logged-in user's saved theme so SSR renders with the right
  // palette from the very first paint — no flash of wrong theme.
  let theme: ThemeName = DEFAULT_THEME;
  try {
    const user = await getCurrentUser();
    if (user && isValidTheme(user.theme)) theme = user.theme;
  } catch {
    // If the backend is down on first paint, fall back silently to default.
  }

  return (
    <html
      lang="en"
      data-theme={theme}
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
