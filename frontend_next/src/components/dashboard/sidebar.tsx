"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Clock,
  Download,
  FilePlus,
  FileText,
  FlaskConical,
  FolderOpen,
  Home,
  type LucideIcon,
  Menu,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ThemeSelector } from "@/components/theme-selector";
import { LogoutButton } from "./logout-button";
import { UsageRibbon } from "./usage-ribbon";
import type { User } from "@/lib/types";
import type { ThemeName } from "@/lib/themes";
import { cn } from "@/lib/utils";

/**
 * Icon registry. The sidebar lives in a Client Component but its `links`
 * prop is constructed inside Server Components (the per-role layouts), and
 * React Server Components can't serialize function references across the
 * boundary. So we pass *names* (strings) from the server and resolve them
 * to actual Lucide components here.
 *
 * Add a key here when you add a new sidebar link to any role.
 */
const ICONS = {
  home: Home,
  folder: FolderOpen,
  fileText: FileText,
  filePlus: FilePlus,
  clock: Clock,
  users: Users,
  analytics: BarChart3,
  permissions: ShieldCheck,
  flask: FlaskConical,
  download: Download,
} satisfies Record<string, LucideIcon>;

export type SidebarIconName = keyof typeof ICONS;

export interface SidebarLink {
  href: string;
  label: string;
  icon: SidebarIconName;
  badge?: number;
}

export function Sidebar({
  user,
  theme,
  links,
  roleBadge,
  children,
}: {
  user: User;
  theme: ThemeName;
  links: SidebarLink[];
  roleBadge: string;
  children?: React.ReactNode;
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
          "fixed inset-y-0 left-0 z-50 flex w-64 flex-col bg-sidebar text-sidebar-foreground border-r border-sidebar-border transition-transform duration-200",
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

        {/* Brand + profile */}
        <div className="px-4 pb-3 pt-5">
          <div className="flex items-center gap-2">
            <span className="text-xl">📚</span>
            <span className="text-sm font-semibold">School LLM</span>
          </div>
          <div className="mt-4 rounded-md border border-sidebar-border bg-black/20 p-3">
            <div className="text-sm font-medium">
              {user.full_name || user.username}
            </div>
            <div className="text-xs text-sidebar-muted">
              {user.email}
            </div>
            <div className="mt-1.5 inline-flex rounded-full bg-primary px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-primary-foreground">
              {roleBadge}
            </div>
          </div>
        </div>

        <Separator className="my-1 bg-sidebar-border" />

        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-2">
          {links.map((l) => {
            const Icon = ICONS[l.icon];
            const isActive =
              pathname === l.href || pathname.startsWith(l.href + "/");
            return (
              <Link
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-primary text-primary-foreground"
                    : "text-sidebar-foreground hover:bg-white/5"
                )}
              >
                <Icon className="h-4 w-4" />
                <span className="flex-1">{l.label}</span>
                {l.badge ? (
                  <span className="rounded-full bg-danger px-1.5 text-[10px] font-bold text-white">
                    {l.badge}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </nav>

        {/* Optional role-specific slot (e.g. teacher subjects list, admin "Refresh All") */}
        {children && (
          <>
            <Separator className="bg-sidebar-border" />
            <div className="px-3 py-3">{children}</div>
          </>
        )}

        <Separator className="bg-sidebar-border" />

        <div className="px-3 py-3">
          <UsageRibbon />
        </div>

        <Separator className="bg-sidebar-border" />

        <div className="space-y-1 px-3 py-3">
          <ThemeSelector currentTheme={theme} />
          <LogoutButton />
        </div>
      </aside>
    </>
  );
}
