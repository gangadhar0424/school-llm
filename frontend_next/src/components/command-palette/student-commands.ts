import type { NavCommand } from "./command-palette";

/** Navigation commands for the student Cmd+K palette. Icons are
 *  referenced by name — see the comment in admin-commands.ts. */
export const STUDENT_COMMANDS: NavCommand[] = [
  {
    id: "student.home",
    label: "Home",
    sublabel: "Dashboard",
    icon: "home",
    href: "/student",
  },
  {
    id: "student.workspace",
    label: "Workspace",
    keywords: "qa quiz summary audio video ai tools",
    icon: "folder",
    href: "/student/workspace",
  },
  {
    id: "student.assignments",
    label: "Assignments",
    keywords: "homework tasks submit",
    icon: "clipboardList",
    href: "/student/assignments",
  },
  {
    id: "student.history",
    label: "History",
    keywords: "past chats sessions",
    icon: "history",
    href: "/student/history",
  },
];
