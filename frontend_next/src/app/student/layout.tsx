import { requireRole } from "@/lib/auth";
import { DEFAULT_THEME, isValidTheme, type ThemeName } from "@/lib/themes";
import { Sidebar, type SidebarLink } from "@/components/dashboard/sidebar";

// Icons are referenced by name (strings) so this array stays serializable
// across the Server → Client boundary when passed to the Sidebar prop.
const LINKS: SidebarLink[] = [
  { href: "/student", label: "Home", icon: "home" },
  { href: "/student/workspace", label: "Workspace", icon: "folder" },
  { href: "/student/assignments", label: "Assignments", icon: "fileText" },
  { href: "/student/history", label: "History", icon: "clock" },
];

export default async function StudentLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireRole("student");
  const theme: ThemeName = isValidTheme(user.theme) ? user.theme : DEFAULT_THEME;

  return (
    <div className="flex min-h-screen flex-1">
      <Sidebar user={user} theme={theme} links={LINKS} roleBadge="Student" />
      <div className="flex flex-1 flex-col">{children}</div>
    </div>
  );
}
