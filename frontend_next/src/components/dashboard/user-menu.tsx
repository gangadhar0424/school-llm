"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { toast } from "sonner";
import { Check, ChevronsUpDown, LogOut, Palette } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { THEMES, type ThemeName } from "@/lib/themes";
import type { User } from "@/lib/types";
import { cn } from "@/lib/utils";

/**
 * Bottom-of-sidebar user identity + dropdown. Replaces the separate
 * ThemeSelector + LogoutButton stack with one compact, professional
 * affordance that mirrors what Linear, Vercel, and Notion do.
 *
 * Click anywhere on the bar → dropdown opens with:
 *   • Theme submenu (4 palettes)
 *   • Logout
 *
 * Avatar = first letter of full_name or username. We never load remote
 * images for it because the ERP `/me/` payload doesn't expose one yet.
 */
export function UserMenu({
  user,
  currentTheme,
  roleBadge,
}: {
  user: User;
  currentTheme: ThemeName;
  roleBadge: string;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [active, setActive] = React.useState<ThemeName>(currentTheme);

  const applyTheme = (name: ThemeName) => {
    // Optimistically swap the data-theme on <html> for instant feedback,
    // then persist server-side. If the persist fails with anything other
    // than 409 (ERP user, expected), roll back the visual change.
    const prev = active;
    setActive(name);
    document.documentElement.setAttribute("data-theme", name);
    // ERP-authenticated users don't store theme prefs on our side — the
    // backend returns 409 for those. Skip the call entirely so we don't
    // flood the console with expected errors. The data-theme override
    // still applies for the current session.
    if (user.auth_source === "eskoolia") return;
    fetch("/api/user/theme", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theme: name }),
    })
      .then((res) => {
        if (!res.ok && res.status !== 409) {
          throw new Error("theme save failed");
        }
      })
      .catch(() => {
        setActive(prev);
        document.documentElement.setAttribute("data-theme", prev);
        toast.error("Could not save theme. Reverted.");
      });
  };

  const onLogout = () => {
    start(async () => {
      await fetch("/api/logout", { method: "POST" });
      router.push("/login");
      router.refresh();
    });
  };

  const initials = getInitials(user.full_name || user.username || user.email);
  const displayName = user.full_name || user.username;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className={cn(
            "group flex w-full items-center gap-2.5 rounded-md border border-transparent",
            "px-2 py-1.5 text-left transition-colors",
            "hover:bg-muted hover:border-border",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
          )}
          aria-label="Account menu"
          disabled={pending}
        >
          <span
            aria-hidden
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-primary-chip text-[11px] font-semibold uppercase tracking-wide text-primary"
          >
            {initials}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-sidebar-foreground">
              {displayName}
            </span>
            <span className="block truncate text-[10px] uppercase tracking-wide text-sidebar-muted">
              {roleBadge}
            </span>
          </span>
          <ChevronsUpDown
            className="h-3.5 w-3.5 shrink-0 text-sidebar-muted transition-opacity group-hover:opacity-100 opacity-60"
            aria-hidden
          />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent
        align="end"
        side="top"
        sideOffset={8}
        className="w-56"
      >
        <DropdownMenuLabel className="truncate">
          {user.email}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        <DropdownMenuLabel className="flex items-center gap-1.5 pb-1 pt-2 text-[10px] uppercase">
          <Palette className="h-3 w-3" /> Theme
        </DropdownMenuLabel>
        {THEMES.map((t) => {
          const isActive = active === t.name;
          return (
            <DropdownMenuItem
              key={t.name}
              onSelect={(e) => {
                // Keep the menu open while picking a palette — most
                // users want to compare two palettes side-by-side.
                e.preventDefault();
                applyTheme(t.name);
              }}
              className="gap-2"
            >
              <span
                className="flex h-3 w-3 shrink-0 rounded-sm border border-border"
                style={{ background: t.preview[2] }}
                aria-hidden
              />
              <span className="flex-1 text-sm">{t.label}</span>
              {isActive && <Check className="h-3.5 w-3.5 text-primary" />}
            </DropdownMenuItem>
          );
        })}

        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={onLogout}
          disabled={pending}
          className="gap-2 text-danger focus:bg-danger/10 focus:text-danger"
        >
          <LogOut className="h-3.5 w-3.5" />
          <span>Log out</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function getInitials(s: string): string {
  const parts = s.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}
