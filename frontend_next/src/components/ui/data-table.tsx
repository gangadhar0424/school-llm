"use client";

import * as React from "react";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  ChevronUp,
  MoreHorizontal,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * Headless-ish data table.
 *
 * Single source of truth for every list view in the admin dashboard.
 * Replaces three separate card-stack implementations (Users · Activity ·
 * PDFs) with one component that sorts, paginates, selects, and exposes
 * row-level actions through a consistent kebab menu.
 *
 * Design rules followed by the visual style:
 *   • Sticky header so sorting + scrolling work together
 *   • Subtle row borders (single `border-b border-border`) — no zebra
 *   • Hover state on rows, *primary-chip* tint on selected
 *   • Column headers in `text-xs uppercase tracking-wider` to read as
 *     metadata, not as content
 *
 * Sort and selection are managed internally unless the caller passes
 * controlled props. Sorting is client-side; for very large data sets,
 * pass already-sorted data and don't mark columns sortable.
 */

export interface DataTableColumn<T> {
  /** Stable key, unique across columns. */
  key: string;
  header: React.ReactNode;
  /** Cell renderer for a single row. */
  cell: (row: T) => React.ReactNode;
  /** Enable click-to-sort on the header. Provide `sortValue` if the
   *  cell content isn't directly comparable. */
  sortable?: boolean;
  sortValue?: (row: T) => string | number | null | undefined;
  /** Optional Tailwind width class (e.g. `"w-32"`). */
  width?: string;
  align?: "left" | "right" | "center";
  /** Tailwind class merged into the `<td>`. */
  cellClassName?: string;
  /** Tailwind class merged into the `<th>`. */
  headerClassName?: string;
}

export interface RowAction {
  label: string;
  icon?: React.ComponentType<{ className?: string }>;
  onClick: () => void;
  disabled?: boolean;
  destructive?: boolean;
}

export interface DataTableProps<T> {
  data: T[];
  columns: DataTableColumn<T>[];
  /** Returns a unique string id for a row. */
  rowKey: (row: T) => string;
  loading?: boolean;
  /** Element to render when `data.length === 0` and not loading. */
  empty?: React.ReactNode;
  pageSize?: number;
  /** Show a checkbox column + bulk selection state. */
  selectable?: boolean;
  selectedIds?: Set<string>;
  onSelectionChange?: (ids: Set<string>) => void;
  /** Right-aligned per-row kebab menu. */
  rowActions?: (row: T) => RowAction[];
  /** Click anywhere on a row (except an interactive cell) to fire this. */
  onRowClick?: (row: T) => void;
  className?: string;
}

type SortDir = "asc" | "desc";

export function DataTable<T>({
  data,
  columns,
  rowKey,
  loading,
  empty,
  pageSize = 20,
  selectable,
  selectedIds: controlledSelected,
  onSelectionChange,
  rowActions,
  onRowClick,
  className,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = React.useState<string | null>(null);
  const [sortDir, setSortDir] = React.useState<SortDir>("asc");
  const [page, setPage] = React.useState(1);
  const [uncontrolledSelected, setUncontrolledSelected] = React.useState<
    Set<string>
  >(new Set());

  const selected = controlledSelected ?? uncontrolledSelected;
  const setSelected = React.useCallback(
    (next: Set<string>) => {
      if (!onSelectionChange) setUncontrolledSelected(next);
      onSelectionChange?.(next);
    },
    [onSelectionChange]
  );

  // Reset to page 1 when sort/filter inputs change. React 19's lint
  // forbids setState in effect bodies, so we use the tracked-prop
  // idiom: compare against snapshotted state during render and reset
  // before the next render commits.
  const [tracked, setTracked] = React.useState({
    sortKey,
    sortDir,
    len: data.length,
  });
  if (
    tracked.sortKey !== sortKey ||
    tracked.sortDir !== sortDir ||
    tracked.len !== data.length
  ) {
    setTracked({ sortKey, sortDir, len: data.length });
    setPage(1);
  }

  // Apply sorting (client-side)
  const sorted = React.useMemo(() => {
    if (!sortKey) return data;
    const col = columns.find((c) => c.key === sortKey);
    if (!col?.sortable) return data;
    const getter = col.sortValue ?? ((row: T) => String(col.cell(row) ?? ""));
    const dir = sortDir === "asc" ? 1 : -1;
    return [...data].sort((a, b) => {
      const va = getter(a);
      const vb = getter(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      if (typeof va === "number" && typeof vb === "number") {
        return (va - vb) * dir;
      }
      return String(va).localeCompare(String(vb)) * dir;
    });
  }, [data, columns, sortKey, sortDir]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pageData = sorted.slice((safePage - 1) * pageSize, safePage * pageSize);

  const allOnPageSelected =
    selectable &&
    pageData.length > 0 &&
    pageData.every((row) => selected.has(rowKey(row)));

  const toggleSortFor = (col: DataTableColumn<T>) => {
    if (!col.sortable) return;
    if (sortKey === col.key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(col.key);
      setSortDir("asc");
    }
  };

  const toggleAllOnPage = () => {
    const next = new Set(selected);
    if (allOnPageSelected) {
      pageData.forEach((row) => next.delete(rowKey(row)));
    } else {
      pageData.forEach((row) => next.add(rowKey(row)));
    }
    setSelected(next);
  };

  const toggleRow = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  // Tailwind: text-right / text-left / text-center
  const alignClass = (a?: "left" | "right" | "center") =>
    a === "right" ? "text-right" : a === "center" ? "text-center" : "text-left";

  return (
    <div className={cn("flex flex-col gap-3", className)}>
      <div className="overflow-x-auto rounded-lg border border-border bg-surface">
        <table className="w-full border-collapse text-sm">
          <thead className="bg-surface-2">
            <tr className="border-b border-border">
              {selectable && (
                <th className="w-9 px-3 py-2.5">
                  <Checkbox
                    aria-label="Select all on this page"
                    checked={allOnPageSelected || false}
                    onCheckedChange={toggleAllOnPage}
                  />
                </th>
              )}
              {columns.map((c) => {
                const isSorted = sortKey === c.key;
                return (
                  <th
                    key={c.key}
                    className={cn(
                      "px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground",
                      alignClass(c.align),
                      c.width,
                      c.headerClassName,
                      c.sortable && "cursor-pointer select-none hover:text-foreground"
                    )}
                    onClick={() => toggleSortFor(c)}
                    aria-sort={
                      isSorted
                        ? sortDir === "asc"
                          ? "ascending"
                          : "descending"
                        : undefined
                    }
                  >
                    <span className="inline-flex items-center gap-1">
                      {c.header}
                      {c.sortable &&
                        (isSorted ? (
                          sortDir === "asc" ? (
                            <ChevronUp className="h-3 w-3" />
                          ) : (
                            <ChevronDown className="h-3 w-3" />
                          )
                        ) : (
                          <ChevronsUpDown className="h-3 w-3 opacity-40" />
                        ))}
                    </span>
                  </th>
                );
              })}
              {rowActions && <th className="w-9 px-3 py-2.5" />}
            </tr>
          </thead>

          <tbody>
            {loading &&
              Array.from({ length: Math.min(pageSize, 6) }).map((_, i) => (
                <tr key={`s-${i}`} className="border-b border-border">
                  {selectable && (
                    <td className="px-3 py-2.5">
                      <Skeleton className="h-4 w-4 rounded" />
                    </td>
                  )}
                  {columns.map((c) => (
                    <td key={c.key} className="px-3 py-2.5">
                      <Skeleton className="h-3.5 w-3/4" />
                    </td>
                  ))}
                  {rowActions && <td className="px-3 py-2.5" />}
                </tr>
              ))}

            {!loading && pageData.length === 0 && (
              <tr>
                <td
                  colSpan={
                    columns.length +
                    (selectable ? 1 : 0) +
                    (rowActions ? 1 : 0)
                  }
                  className="px-3 py-12 text-center text-sm text-muted-foreground"
                >
                  {empty ?? "No data."}
                </td>
              </tr>
            )}

            {!loading &&
              pageData.map((row) => {
                const id = rowKey(row);
                const isSelected = selected.has(id);
                return (
                  <tr
                    key={id}
                    className={cn(
                      "border-b border-border transition-colors last:border-b-0",
                      isSelected
                        ? "bg-primary-chip"
                        : "hover:bg-muted/60",
                      onRowClick && "cursor-pointer"
                    )}
                    onClick={(e) => {
                      // Don't fire onRowClick when clicking an interactive
                      // element inside a cell (checkbox, kebab menu, etc.)
                      if (
                        (e.target as HTMLElement).closest(
                          'button,input,a,[role="menuitem"]'
                        )
                      ) {
                        return;
                      }
                      onRowClick?.(row);
                    }}
                  >
                    {selectable && (
                      <td className="px-3 py-2.5">
                        <Checkbox
                          aria-label={`Select row`}
                          checked={isSelected}
                          onCheckedChange={() => toggleRow(id)}
                        />
                      </td>
                    )}
                    {columns.map((c) => (
                      <td
                        key={c.key}
                        className={cn(
                          "px-3 py-2.5",
                          alignClass(c.align),
                          c.cellClassName
                        )}
                      >
                        {c.cell(row)}
                      </td>
                    ))}
                    {rowActions && (
                      <td className="px-3 py-2.5 text-right">
                        <RowActionsMenu actions={rowActions(row)} />
                      </td>
                    )}
                  </tr>
                );
              })}
          </tbody>
        </table>
      </div>

      {/* Pagination + selection summary */}
      {(sorted.length > pageSize || selected.size > 0) && (
        <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
          <div>
            {selectable && selected.size > 0 ? (
              <span className="font-medium text-foreground">
                {selected.size} selected
              </span>
            ) : (
              <span>
                Showing{" "}
                {sorted.length === 0
                  ? 0
                  : (safePage - 1) * pageSize + 1}
                –{Math.min(safePage * pageSize, sorted.length)} of{" "}
                {sorted.length}
              </span>
            )}
          </div>
          {sorted.length > pageSize && (
            <div className="flex items-center gap-1">
              <Button
                size="sm"
                variant="ghost"
                disabled={safePage === 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                aria-label="Previous page"
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              <span className="px-2">
                Page {safePage} of {totalPages}
              </span>
              <Button
                size="sm"
                variant="ghost"
                disabled={safePage === totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                aria-label="Next page"
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function RowActionsMenu({ actions }: { actions: RowAction[] }) {
  if (actions.length === 0) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7"
          aria-label="Row actions"
        >
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-35">
        {actions.map((a, i) => {
          const Icon = a.icon;
          return (
            <DropdownMenuItem
              key={i}
              disabled={a.disabled}
              onSelect={a.onClick}
              className={cn(
                "gap-2",
                a.destructive && "text-danger focus:bg-danger/10 focus:text-danger"
              )}
            >
              {Icon && <Icon className="h-3.5 w-3.5" />}
              {a.label}
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
