import { requireRole } from "@/lib/auth";
import { DEFAULT_THEME, isValidTheme, type ThemeName } from "@/lib/themes";
import { Sidebar, type SidebarGroup } from "@/components/dashboard/sidebar";

const GROUPS: SidebarGroup[] = [
  {
    label: "Platform",
    links: [
      { href: "/super-admin", label: "Overview", icon: "analytics" },
      { href: "/super-admin/schools", label: "Schools", icon: "school" },
      {
        href: "/super-admin/rate-limits",
        label: "Default limits",
        icon: "clockFading",
      },
    ],
  },
];

export default async function SuperAdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireRole("super_admin");
  const theme: ThemeName = isValidTheme(user.theme) ? user.theme : DEFAULT_THEME;

  return (
    <div className="flex min-h-screen flex-1">
      <Sidebar
        user={user}
        theme={theme}
        groups={GROUPS}
        roleBadge="Super Admin"
      />
      <div className="flex flex-1 flex-col">{children}</div>
    </div>
  );
}
