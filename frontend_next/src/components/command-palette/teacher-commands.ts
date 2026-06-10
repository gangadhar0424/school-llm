import type { NavCommand } from "./command-palette";

/** Navigation commands for the teacher Cmd+K palette. Icons are
 *  referenced by name — see the comment in admin-commands.ts. */
export const TEACHER_COMMANDS: NavCommand[] = [
  {
    id: "teacher.home",
    label: "Home",
    sublabel: "Dashboard",
    icon: "home",
    href: "/teacher",
  },
  {
    id: "teacher.assignments",
    label: "My Assignments",
    keywords: "list created grading",
    icon: "fileText",
    href: "/teacher/assignments",
  },
  {
    id: "teacher.new-assignment",
    label: "New Assignment",
    keywords: "create author publish",
    icon: "filePlus",
    href: "/teacher/new-assignment",
  },
  {
    id: "teacher.students",
    label: "My Students",
    keywords: "class roster",
    icon: "users",
    href: "/teacher/students",
  },
];
