"use client";

import * as React from "react";
import { Info } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

/**
 * Small read-only badge that displays an ERP role title ("Class Teacher",
 * "HOD", "Vice Principal", etc.) with a hover/click popover explaining
 * that the value is managed in the school's ERP and can't be edited
 * here. Falls back to "—" if no title is available.
 *
 * Used on the Teachers list, Students drilldown sheet, and anywhere the
 * raw ERP role surfaces in the admin UI.
 */
export function ErpTitleBadge({
  title,
  className,
}: {
  title: string | null | undefined;
  className?: string;
}) {
  if (!title) {
    return (
      <span className={`text-xs text-muted-foreground ${className ?? ""}`}>
        —
      </span>
    );
  }
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={`inline-flex items-center gap-1 align-middle ${className ?? ""}`}
          aria-label={`${title} — managed in ERP`}
        >
          <Badge variant="outline" className="cursor-help font-normal">
            {title}
            <Info className="ml-1 h-3 w-3 text-muted-foreground" />
          </Badge>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64 text-xs">
        <p className="font-medium">Managed in the school&apos;s ERP</p>
        <p className="mt-1 text-muted-foreground">
          This role title comes from the school&apos;s identity provider.
          To change it, update the user in the ERP — the LLM will pick up
          the new title on their next login.
        </p>
      </PopoverContent>
    </Popover>
  );
}
