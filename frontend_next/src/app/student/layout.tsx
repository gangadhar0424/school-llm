import { requireRole } from "@/lib/auth";
import { DEFAULT_THEME, isValidTheme, type ThemeName } from "@/lib/themes";
import { Sidebar, type SidebarGroup } from "@/components/dashboard/sidebar";
import { UsageRibbon } from "@/components/dashboard/usage-ribbon";
import { CommandPalette } from "@/components/command-palette/command-palette";
import { STUDENT_COMMANDS } from "@/components/command-palette/student-commands";

// Student nav fits on one screen — single ungrouped section.
const GROUPS: SidebarGroup[] = [
  {
    links: [
      { href: "/student", label: "Home", icon: "home" },
      { href: "/student/workspace", label: "Workspace", icon: "folder" },
      { href: "/student/assignments", label: "Assignments", icon: "fileText" },
      { href: "/student/history", label: "History", icon: "history" },
    ],
  },
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
      <Sidebar
        user={user}
        theme={theme}
        groups={GROUPS}
        roleBadge="Student"
        bottomSlot={<UsageRibbon />}
      />
      <div className="flex flex-1 flex-col">{children}</div>
      <CommandPalette navigationCommands={STUDENT_COMMANDS} />
    </div>
  );
}
