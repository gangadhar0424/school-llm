"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Check, Palette } from "lucide-react";
import { THEMES, type ThemeName } from "@/lib/themes";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Theme switcher rendered in the sidebar. Sets `data-theme` on <html>
 * immediately for instant visual feedback, then persists the choice to
 * the backend via PUT /api/auth/theme so it survives logout + login from
 * any device.
 */
export function ThemeSelector({
  currentTheme,
}: {
  currentTheme: ThemeName;
}) {
  const router = useRouter();
  const [active, setActive] = React.useState<ThemeName>(currentTheme);
  const [pending, startTransition] = React.useTransition();

  const applyTheme = (next: ThemeName) => {
    if (next === active) return;
    // Optimistic UI: flip the data-theme attribute immediately.
    document.documentElement.setAttribute("data-theme", next);
    setActive(next);

    startTransition(async () => {
      try {
        const res = await fetch("/api/user/theme", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ theme: next }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.error || "Could not save theme");
        }
        // Refresh server components so any SSR-rendered theme metadata
        // (e.g. the html data-theme on the next reload) stays consistent.
        router.refresh();
      } catch (e) {
        // Roll back the optimistic update on failure.
        document.documentElement.setAttribute("data-theme", active);
        setActive(active);
        toast.error(
          e instanceof Error ? e.message : "Failed to save theme — reverted."
        );
      }
    });
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="w-full justify-start gap-2 text-sidebar-foreground hover:bg-white/5"
          disabled={pending}
        >
          <Palette className="h-4 w-4" />
          <span>Theme</span>
          <span className="ml-auto text-xs text-sidebar-muted">
            {THEMES.find((t) => t.name === active)?.label}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>Choose a theme</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {THEMES.map((t) => (
          <DropdownMenuItem
            key={t.name}
            onSelect={(e) => {
              e.preventDefault();
              applyTheme(t.name);
            }}
            className="flex items-center gap-3"
          >
            <span className="text-base">{t.emoji}</span>
            <div className="flex flex-1 flex-col">
              <span className="text-sm font-medium">{t.label}</span>
              <span className="text-xs text-muted-foreground">
                {t.description}
              </span>
            </div>
            <div className="flex gap-0.5">
              {t.preview.map((c) => (
                <span
                  key={c}
                  className="h-3 w-3 rounded-sm border border-border"
                  style={{ background: c }}
                />
              ))}
            </div>
            <Check
              className={cn(
                "ml-1 h-4 w-4",
                active === t.name ? "opacity-100" : "opacity-0"
              )}
            />
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
