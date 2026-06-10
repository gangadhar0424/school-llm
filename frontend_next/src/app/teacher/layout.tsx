import { requireRole } from "@/lib/auth";
import { DEFAULT_THEME, isValidTheme, type ThemeName } from "@/lib/themes";
import { Sidebar, type SidebarGroup } from "@/components/dashboard/sidebar";
import { UsageRibbon } from "@/components/dashboard/usage-ribbon";
import { CommandPalette } from "@/components/command-palette/command-palette";
import { TEACHER_COMMANDS } from "@/components/command-palette/teacher-commands";

// Teacher nav fits on one screen — single ungrouped section.
const GROUPS: SidebarGroup[] = [
  {
    links: [
      { href: "/teacher", label: "Home", icon: "home" },
      { href: "/teacher/assignments", label: "My Assignments", icon: "fileText" },
      { href: "/teacher/new-assignment", label: "New Assignment", icon: "filePlus" },
      { href: "/teacher/students", label: "My Students", icon: "users" },
    ],
  },
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
        groups={GROUPS}
        roleBadge="Teacher"
        bottomSlot={<UsageRibbon />}
      />
      <div className="flex flex-1 flex-col">{children}</div>
      <CommandPalette navigationCommands={TEACHER_COMMANDS} />
    </div>
  );
}
