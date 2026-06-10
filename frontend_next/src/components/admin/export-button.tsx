"use client";

import * as React from "react";
import { Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { downloadCsv, type ExportOptions } from "@/lib/csv-export";

/**
 * Page-level "Export this view" button. Designed to live in the
 * DashboardHeader's `actions` slot so it sits to the left of the school
 * chip and the notification/chat bells across every admin page.
 *
 * Pass it the same rows the table is rendering (already filtered and
 * sorted by the page's state) and a column definition; clicking the
 * button builds the CSV in-memory and triggers a download. No backend
 * round-trip, so it works instantly regardless of network.
 */
export function ExportButton<T>({
  label = "Export",
  loading,
  disabled,
  options,
}: {
  label?: string;
  /** Suppress the button while the page's data is still fetching. */
  loading?: boolean;
  /** Disable the button (e.g. no rows to export). */
  disabled?: boolean;
  options: ExportOptions<T> | (() => ExportOptions<T>);
}) {
  const onClick = React.useCallback(() => {
    const opts = typeof options === "function" ? options() : options;
    downloadCsv(opts);
  }, [options]);

  const isDisabled = !!loading || !!disabled;
  return (
    <Button
      variant="outline"
      size="sm"
      onClick={onClick}
      disabled={isDisabled}
      title="Download the current view as a CSV file"
    >
      <Download className="h-3.5 w-3.5" />
      {label}
    </Button>
  );
}
