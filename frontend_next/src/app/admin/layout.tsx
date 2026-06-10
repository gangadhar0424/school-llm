import { requireRole } from "@/lib/auth";
import { DEFAULT_THEME, isValidTheme, type ThemeName } from "@/lib/themes";
import { Sidebar, type SidebarLink } from "@/components/dashboard/sidebar";

// Icons are passed as names (strings) — see student/layout.tsx for why.
const LINKS: SidebarLink[] = [
  { href: "/admin", label: "Analytics", icon: "analytics" },
  { href: "/admin/users", label: "Users", icon: "users" },
  { href: "/admin/permissions", label: "Roles & Permissions", icon: "permissions" },
  { href: "/admin/rate-limits", label: "Rate Limits", icon: "clock" },
  { href: "/admin/activity", label: "Activity", icon: "clock" },
  { href: "/admin/pdfs", label: "All PDFs", icon: "fileText" },
  { href: "/admin/eval", label: "AI Evaluation", icon: "flask" },
  { href: "/admin/export", label: "Export", icon: "download" },
];

export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireRole("admin");
  const theme: ThemeName = isValidTheme(user.theme) ? user.theme : DEFAULT_THEME;

  return (
    <div className="flex min-h-screen flex-1">
      <Sidebar user={user} theme={theme} links={LINKS} roleBadge="Admin" />
      <div className="flex flex-1 flex-col">{children}</div>
    </div>
  );
}
