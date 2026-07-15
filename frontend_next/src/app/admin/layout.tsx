import { requireRole } from "@/lib/auth";
import { DEFAULT_THEME, isValidTheme, type ThemeName } from "@/lib/themes";
import { Sidebar, type SidebarGroup } from "@/components/dashboard/sidebar";
import { CommandPalette } from "@/components/command-palette/command-palette";
import { ADMIN_COMMANDS } from "@/components/command-palette/admin-commands";

// Sidebar groups for the admin shell. "Overview" carries the high-level
// school-shaped views (analytics, school card, org chart, activity feed).
// "People" replaces the old flat "Users" with three role-segmented
// destinations (Teachers / Students / Staff) sitting next to the
// permission + rate-limit tooling that governs them. "Resources" stays
// as the content / observability bucket.
const GROUPS: SidebarGroup[] = [
  {
    label: "Overview",
    links: [
      { href: "/admin", label: "Analytics", icon: "analytics" },
      { href: "/admin/school", label: "School", icon: "school" },
      { href: "/admin/org", label: "Org chart", icon: "orgChart" },
      { href: "/admin/activity", label: "Activity", icon: "history" },
    ],
  },
  {
    label: "People",
    links: [
      { href: "/admin/teachers", label: "Teachers", icon: "graduationCap" },
      { href: "/admin/students", label: "Students", icon: "book" },
      { href: "/admin/permissions", label: "Permissions", icon: "permissions" },
    ],
  },
  {
    label: "Resources",
    links: [
      { href: "/admin/assignments", label: "Assignments", icon: "book" },
      { href: "/admin/pdfs", label: "PDFs", icon: "fileText" },
      { href: "/admin/eval", label: "AI Evaluation", icon: "flask" },
    ],
  },
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
      <Sidebar user={user} theme={theme} groups={GROUPS} roleBadge="Administrator" />
      <div className="flex flex-1 flex-col">{children}</div>
      {/* Cmd/Ctrl+K palette — owns its own open state and global hotkey
          listener; just mount it once at the layout level. */}
      <CommandPalette navigationCommands={ADMIN_COMMANDS} />
    </div>
  );
}
