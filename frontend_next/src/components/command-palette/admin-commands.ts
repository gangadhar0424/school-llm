import type { NavCommand } from "./command-palette";

/**
 * Navigation commands surfaced in the admin Cmd+K palette. Adding a new
 * admin page? Drop an entry here and the palette picks it up — no need
 * to touch the layout.
 *
 * Icons are referenced by name (see `NAV_ICONS` in command-palette.tsx)
 * because this module is imported into a Server Component and RSC can't
 * serialize React component references across the boundary.
 *
 * Order mirrors the sidebar groups (Overview → People → Resources) so
 * unfiltered palette results read in the same order as the nav.
 */
export const ADMIN_COMMANDS: NavCommand[] = [
  // ── Overview ─────────────────────────────────────────────────────────
  {
    id: "admin.analytics",
    label: "Analytics",
    sublabel: "Dashboard overview",
    icon: "analytics",
    href: "/admin",
  },
  {
    id: "admin.school",
    label: "School",
    sublabel: "Headcount and pulse",
    keywords: "overview headcount teachers students active",
    icon: "school",
    href: "/admin/school",
  },
  {
    id: "admin.org",
    label: "Org chart",
    sublabel: "Who teaches whom",
    keywords: "relationships graph classes subjects teachers",
    icon: "orgChart",
    href: "/admin/org",
  },
  {
    id: "admin.activity",
    label: "Activity",
    sublabel: "Audit trail",
    icon: "activity",
    href: "/admin/activity",
  },

  // ── People ───────────────────────────────────────────────────────────
  {
    id: "admin.teachers",
    label: "Teachers",
    keywords: "faculty staff teaching classes subjects",
    icon: "graduationCap",
    href: "/admin/teachers",
  },
  {
    id: "admin.students",
    label: "Students",
    keywords: "learners pupils class section",
    icon: "book",
    href: "/admin/students",
  },
  {
    id: "admin.permissions",
    label: "Permissions",
    keywords: "roles rbac toggle",
    icon: "permissions",
    href: "/admin/permissions",
  },
  {
    id: "admin.rate-limits",
    label: "Rate limits",
    keywords: "quota caps limits",
    icon: "clock",
    href: "/admin/rate-limits",
  },

  // ── Resources ────────────────────────────────────────────────────────
  {
    id: "admin.pdfs",
    label: "PDFs",
    keywords: "documents files uploads",
    icon: "fileText",
    href: "/admin/pdfs",
  },
  {
    id: "admin.eval",
    label: "AI Evaluation",
    keywords: "ai eval scores runs",
    icon: "flask",
    href: "/admin/eval",
  },
];
