"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Activity,
  ArrowRight,
  BarChart3,
  BookOpen,
  Briefcase,
  ClipboardList,
  Clock,
  Download,
  FilePlus,
  FileText,
  FlaskConical,
  FolderOpen,
  GraduationCap,
  History,
  Home,
  LogOut,
  Network,
  Palette,
  School,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
  type LucideIcon,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";
import { THEMES, type ThemeName } from "@/lib/themes";
import { useCurrentUser } from "@/lib/use-current-user";
import { cn } from "@/lib/utils";

/**
 * Cmd/Ctrl + K command palette — global "jump to" surface usable from
 * every role's dashboard.
 *
 * The caller provides the navigation commands appropriate for the role
 * (admin pages, student pages, etc.). The palette adds two universal
 * groups on top: theme switching and logout. This way one component
 * works for every layout without each one importing every page's icon
 * set.
 *
 * Implementation notes:
 *  - Theme PUT is silently skipped for ERP-authenticated users (the
 *    backend would return 409 because their identity provider owns
 *    the prefs). The client-side `data-theme` change still applies
 *    for the current session, which matches the UserMenu's behaviour.
 *  - Pure React + Radix Dialog. No `cmdk` dependency — ~250 lines of
 *    keyboard handling and grouping logic is cheaper than the bundle.
 */

export interface CommandDef {
  id: string;
  label: string;
  sublabel?: string;
  /** Free-text shadow string used for matching when the label alone
   *  isn't enough (synonyms, related concepts). */
  keywords?: string;
  icon: LucideIcon;
  onSelect: () => void;
}

/** Icon registry for nav commands. Per-role command files live in
 *  Server Components (the role layouts import them), and RSC can't
 *  serialize React component references across the boundary — see the
 *  matching pattern in `sidebar.tsx`. So callers pass a string name and
 *  we resolve it to a Lucide component here. */
const NAV_ICONS = {
  activity: Activity,
  analytics: BarChart3,
  book: BookOpen,
  briefcase: Briefcase,
  clipboardList: ClipboardList,
  clock: Clock,
  download: Download,
  filePlus: FilePlus,
  fileText: FileText,
  flask: FlaskConical,
  folder: FolderOpen,
  graduationCap: GraduationCap,
  history: History,
  home: Home,
  orgChart: Network,
  permissions: ShieldCheck,
  school: School,
  users: Users,
} satisfies Record<string, LucideIcon>;

export type NavIconName = keyof typeof NAV_ICONS;

/** Caller-friendly shorthand for navigation entries. Per-role command
 *  files (admin-commands, student-commands, teacher-commands) export
 *  arrays of these. The palette wraps each into a CommandDef with an
 *  `onSelect` that navigates via `router.push(href)`. */
export type NavCommand = {
  id: string;
  label: string;
  sublabel?: string;
  keywords?: string;
  icon: NavIconName;
  href: string;
};

interface Group {
  id: string;
  label: string;
  commands: CommandDef[];
}

export function CommandPalette({
  navigationCommands,
}: {
  navigationCommands: NavCommand[];
}) {
  const router = useRouter();
  const user = useCurrentUser();
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(0);
  const listRef = React.useRef<HTMLDivElement | null>(null);

  // Global hotkey
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Reset state on open. React 19 forbids setState in effect bodies,
  // so use the tracked-prop idiom.
  const [trackedOpen, setTrackedOpen] = React.useState(false);
  if (trackedOpen !== open) {
    setTrackedOpen(open);
    if (open) {
      setQuery("");
      setActiveIndex(0);
    }
  }

  const isErpUser = user?.auth_source === "eskoolia";

  const applyTheme = React.useCallback(
    (name: ThemeName) => {
      // Apply visually for the current session regardless of backend
      // support. Persisting only matters across reloads.
      document.documentElement.setAttribute("data-theme", name);
      setOpen(false);
      if (isErpUser) return; // ERP owns prefs; backend would return 409.
      fetch("/api/user/theme", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme: name }),
      }).then((res) => {
        if (!res.ok && res.status !== 409) {
          toast.error("Could not save theme.");
        }
      });
    },
    [isErpUser]
  );

  const doLogout = React.useCallback(() => {
    setOpen(false);
    fetch("/api/logout", { method: "POST" }).then(() => {
      router.push("/login");
      router.refresh();
    });
  }, [router]);

  // Build the full groups list: caller's nav commands first, then the
  // universal theme + account groups.
  const groups: Group[] = React.useMemo(
    () => [
      {
        id: "navigate",
        label: "Navigate",
        commands: navigationCommands.map((n) => ({
          id: n.id,
          label: n.label,
          sublabel: n.sublabel,
          keywords: n.keywords,
          icon: NAV_ICONS[n.icon],
          onSelect: () => router.push(n.href),
        })),
      },
      {
        id: "theme",
        label: "Theme",
        commands: THEMES.map((t) => ({
          id: `theme.${t.name}`,
          label: t.label,
          sublabel: t.description,
          keywords: `theme palette color ${t.name}`,
          icon: Palette,
          onSelect: () => applyTheme(t.name),
        })),
      },
      {
        id: "account",
        label: "Account",
        commands: [
          {
            id: "account.logout",
            label: "Log out",
            keywords: "sign out exit",
            icon: LogOut,
            onSelect: doLogout,
          },
        ],
      },
    ],
    [navigationCommands, router, applyTheme, doLogout]
  );

  // Filter (preserving group structure)
  const q = query.trim().toLowerCase();
  const filteredGroups = groups
    .map((g) => ({
      ...g,
      commands: g.commands.filter((cmd) => {
        if (!q) return true;
        const hay =
          `${cmd.label} ${cmd.sublabel ?? ""} ${cmd.keywords ?? ""}`.toLowerCase();
        return hay.includes(q);
      }),
    }))
    .filter((g) => g.commands.length > 0);

  const flat = filteredGroups.flatMap((g) => g.commands);
  const active = flat[activeIndex];

  // Clamp activeIndex when the result list shrinks.
  const [trackedLen, setTrackedLen] = React.useState(flat.length);
  if (trackedLen !== flat.length) {
    setTrackedLen(flat.length);
    if (activeIndex >= flat.length) setActiveIndex(Math.max(0, flat.length - 1));
  }

  const onKeyDown: React.KeyboardEventHandler = (e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(flat.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (active) {
        setOpen(false);
        active.onSelect();
      }
    }
  };

  React.useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelector<HTMLElement>(
      `[data-command-index="${activeIndex}"]`
    );
    el?.scrollIntoView({ block: "nearest" });
  }, [activeIndex]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        className="top-[18%] max-w-lg translate-y-0 gap-0 overflow-hidden p-0"
        description="Type to search for a destination or action."
        onKeyDown={onKeyDown}
      >
        <DialogTitle className="sr-only">Command palette</DialogTitle>

        <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
          <Search className="h-4 w-4 text-muted-foreground" />
          <input
            autoFocus
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            placeholder="Type a command or search…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <kbd className="ml-1 rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
            ESC
          </kbd>
        </div>

        <div ref={listRef} className="max-h-[60vh] overflow-y-auto py-1.5">
          {filteredGroups.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">
              No commands match &quot;{query}&quot;.
            </div>
          ) : (
            filteredGroups.map((group) => {
              let groupStart = 0;
              for (const g of filteredGroups) {
                if (g.id === group.id) break;
                groupStart += g.commands.length;
              }
              return (
                <div key={group.id} className="mb-1 last:mb-0">
                  <div className="px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {group.label}
                  </div>
                  {group.commands.map((cmd, i) => {
                    const idx = groupStart + i;
                    const isActive = idx === activeIndex;
                    const Icon = cmd.icon;
                    return (
                      <button
                        key={cmd.id}
                        data-command-index={idx}
                        type="button"
                        onMouseEnter={() => setActiveIndex(idx)}
                        onClick={() => {
                          setOpen(false);
                          cmd.onSelect();
                        }}
                        className={cn(
                          "flex w-full items-center gap-3 px-3 py-2 text-left text-sm transition-colors",
                          isActive
                            ? "bg-primary-chip text-primary"
                            : "text-foreground"
                        )}
                      >
                        <Icon
                          className={cn(
                            "h-4 w-4 shrink-0",
                            isActive
                              ? "text-primary"
                              : "text-muted-foreground"
                          )}
                        />
                        <span className="flex-1 truncate">{cmd.label}</span>
                        {cmd.sublabel && (
                          <span
                            className={cn(
                              "truncate text-xs",
                              isActive
                                ? "text-primary/80"
                                : "text-muted-foreground"
                            )}
                          >
                            {cmd.sublabel}
                          </span>
                        )}
                        {isActive && (
                          <ArrowRight className="h-3 w-3 shrink-0 text-primary" />
                        )}
                      </button>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-border bg-surface-2 px-3 py-1.5 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <Sparkles className="h-3 w-3" />
            Quick actions
          </span>
          <span className="flex items-center gap-2">
            <span>
              <Kbd>↑</Kbd>
              <Kbd>↓</Kbd> navigate
            </span>
            <span>
              <Kbd>↵</Kbd> select
            </span>
          </span>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="mx-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded border border-border bg-muted px-1 text-[9px] font-medium text-muted-foreground">
      {children}
    </kbd>
  );
}
