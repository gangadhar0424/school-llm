"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  BookOpen,
  Briefcase,
  Clock,
  ClockFading,
  Download,
  FilePlus,
  FileText,
  FlaskConical,
  FolderOpen,
  GraduationCap,
  History,
  Home,
  type LucideIcon,
  Menu,
  Network,
  School,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { UserMenu } from "./user-menu";
import type { User } from "@/lib/types";
import type { ThemeName } from "@/lib/themes";
import { cn } from "@/lib/utils";

/**
 * Icon registry. The sidebar lives in a Client Component but its `links`
 * prop is constructed inside Server Components (the per-role layouts),
 * and React Server Components can't serialize function references across
 * the boundary. So we pass *names* (strings) from the server and resolve
 * them to actual Lucide components here.
 *
 * Outline icons only — no emoji — to keep the admin chrome professional.
 */
const ICONS = {
  home: Home,
  folder: FolderOpen,
  fileText: FileText,
  filePlus: FilePlus,
  clock: Clock,
  clockFading: ClockFading,
  history: History,
  users: Users,
  analytics: BarChart3,
  permissions: ShieldCheck,
  flask: FlaskConical,
  download: Download,
  book: BookOpen,
  school: School,
  orgChart: Network,
  graduationCap: GraduationCap,
  briefcase: Briefcase,
} satisfies Record<string, LucideIcon>;

export type SidebarIconName = keyof typeof ICONS;

export interface SidebarLink {
  href: string;
  label: string;
  icon: SidebarIconName;
  /** Optional small count rendered as a chip on the right (e.g. "142"). */
  badge?: number | string;
}

export interface SidebarGroup {
  /** Optional uppercase section label. Omit for flat lists. */
  label?: string;
  links: SidebarLink[];
}

export function Sidebar({
  user,
  theme,
  groups,
  roleBadge,
  bottomSlot,
}: {
  user: User;
  theme: ThemeName;
  groups: SidebarGroup[];
  roleBadge: string;
  /** Optional content shown above the user menu (e.g. UsageRibbon for
   *  students and teachers). Admin omits it. */
  bottomSlot?: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(false);
  const pathname = usePathname();

  return (
    <>
      {/* Mobile toggle (top-left). The desktop sidebar is always visible. */}
      <Button
        size="icon"
        variant="ghost"
        className="fixed left-3 top-3 z-40 md:hidden"
        onClick={() => setOpen(true)}
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </Button>

      {/* Mobile overlay */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
          onClick={() => setOpen(false)}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-60 flex-col bg-sidebar text-sidebar-foreground",
          "border-r border-sidebar-border transition-transform duration-200",
          "md:translate-x-0 md:static md:z-auto",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Mobile close */}
        <Button
          size="icon"
          variant="ghost"
          className="absolute right-2 top-2 md:hidden"
          onClick={() => setOpen(false)}
          aria-label="Close menu"
        >
          <X className="h-4 w-4" />
        </Button>

        {/* Brand */}
        <div className="flex h-14 shrink-0 items-center gap-2 border-b border-sidebar-border px-4">
          <span
            aria-hidden
            className="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-primary-foreground"
          >
            <BookOpen className="h-3.5 w-3.5" />
          </span>
          <span className="text-sm font-semibold tracking-tight">
            School LLM
          </span>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto px-2 py-3">
          {groups.map((group, gi) => (
            <div key={gi} className={gi > 0 ? "mt-4" : ""}>
              {group.label && (
                <div className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-sidebar-muted">
                  {group.label}
                </div>
              )}
              <ul className="space-y-0.5">
                {group.links.map((l) => {
                  const Icon = ICONS[l.icon];
                  const isActive =
                    pathname === l.href || pathname.startsWith(l.href + "/");
                  return (
                    <li key={l.href}>
                      <Link
                        href={l.href}
                        onClick={() => setOpen(false)}
                        className={cn(
                          "group flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors",
                          isActive
                            ? "bg-primary-chip text-primary font-medium"
                            : "text-sidebar-foreground hover:bg-muted"
                        )}
                      >
                        <Icon
                          className={cn(
                            "h-4 w-4 shrink-0",
                            isActive
                              ? "text-primary"
                              : "text-sidebar-muted group-hover:text-sidebar-foreground"
                          )}
                        />
                        <span className="flex-1 truncate">{l.label}</span>
                        {l.badge !== undefined && l.badge !== 0 && (
                          <span
                            className={cn(
                              "rounded-md px-1.5 text-[10px] font-medium",
                              isActive
                                ? "bg-primary/15 text-primary"
                                : "bg-muted text-sidebar-muted"
                            )}
                          >
                            {l.badge}
                          </span>
                        )}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* Optional usage panel for student/teacher; admins omit it. */}
        {bottomSlot && (
          <div className="border-t border-sidebar-border px-2 py-3">
            {bottomSlot}
          </div>
        )}

        {/* User menu — collapses former theme selector + logout */}
        <div className="border-t border-sidebar-border p-2">
          <UserMenu user={user} currentTheme={theme} roleBadge={roleBadge} />
        </div>
      </aside>
    </>
  );
}
