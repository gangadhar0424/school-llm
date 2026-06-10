import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Shared empty state. Use this instead of ad-hoc "No X yet."
 * paragraphs so every "nothing here" surface in the dashboard reads
 * the same way.
 *
 *   <EmptyState
 *     icon={<Users className="h-6 w-6" />}
 *     title="No students yet"
 *     description="Ask the admin to add you to a class."
 *     action={<Button>...</Button>}
 *   />
 *
 * Pattern: outline icon · headline · one-line description · optional
 * action. Centered, generous padding so it feels intentional rather
 * than a bare error.
 */
export interface EmptyStateProps {
  icon?: React.ReactNode;
  title: React.ReactNode;
  description?: React.ReactNode;
  /** Optional CTA (button, link, etc) — renders below the description. */
  action?: React.ReactNode;
  className?: string;
  /** Tighter spacing for inline use inside an already-padded container. */
  compact?: boolean;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  compact = false,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center text-center",
        compact ? "gap-2 py-6" : "gap-3 py-12",
        className
      )}
    >
      {icon && (
        <span
          aria-hidden
          className={cn(
            "inline-flex items-center justify-center rounded-md bg-muted text-muted-foreground",
            compact ? "h-8 w-8" : "h-10 w-10"
          )}
        >
          {icon}
        </span>
      )}
      <div className="space-y-1">
        <p className="text-sm font-medium text-foreground">{title}</p>
        {description && (
          <p className="max-w-md text-xs text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {action && <div className="mt-1">{action}</div>}
    </div>
  );
}
