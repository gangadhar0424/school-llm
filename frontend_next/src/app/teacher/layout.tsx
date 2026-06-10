import { requireRole } from "@/lib/auth";
import { DEFAULT_THEME, isValidTheme, type ThemeName } from "@/lib/themes";
import { Sidebar, type SidebarLink } from "@/components/dashboard/sidebar";

// Icons are passed as names (strings) — see student/layout.tsx for why.
const LINKS: SidebarLink[] = [
  { href: "/teacher", label: "Home", icon: "home" },
  { href: "/teacher/assignments", label: "My Assignments", icon: "fileText" },
  { href: "/teacher/new-assignment", label: "New Assignment", icon: "filePlus" },
  { href: "/teacher/students", label: "My Students", icon: "users" },
];

export default async function TeacherLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireRole("teacher");
  const theme: ThemeName = isValidTheme(user.theme) ? user.theme : DEFAULT_THEME;

  return (
    <div className="flex min-h-screen flex-1">
      <Sidebar
        user={user}
        theme={theme}
        links={LINKS}
        roleBadge="Teacher"
      />
      <div className="flex flex-1 flex-col">{children}</div>
    </div>
  );
}
