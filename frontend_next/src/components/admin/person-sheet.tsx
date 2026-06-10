"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { ArrowRight, UserCircle } from "lucide-react";
import { api } from "@/lib/client-api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { ErpTitleBadge } from "./erp-title-badge";

/**
 * Canonical "person panel" surfaced anywhere the admin clicks a user
 * email or name in the dashboard (Activity feed, future Top-5 strips,
 * etc). Looks the user up by email, then routes the *open* deep-dive to
 * the existing Teachers / Students drilldown pages — so we don't keep
 * two parallel rendering paths for the same data.
 *
 * The sheet itself shows the minimal "who is this?" header and a
 * primary action: "Open profile". For richer detail, the user lands on
 * the role-appropriate page.
 */
export function PersonSheet({
  email,
  open,
  onOpenChange,
}: {
  email: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent description="Who this person is, and a link to their full profile.">
        {email && <PersonSheetBody email={email} onClose={() => onOpenChange(false)} />}
      </SheetContent>
    </Sheet>
  );
}

function PersonSheetBody({
  email,
  onClose,
}: {
  email: string;
  onClose: () => void;
}) {
  const router = useRouter();
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-user-lookup", email],
    queryFn: () => api.adminUserLookup(email),
    retry: false,
  });

  if (isLoading) {
    return (
      <>
        <SheetHeader>
          <SheetTitle>Loading…</SheetTitle>
        </SheetHeader>
        <SheetBody>
          <Skeleton className="h-20 w-full" />
        </SheetBody>
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <SheetHeader>
          <SheetTitle>{email}</SheetTitle>
        </SheetHeader>
        <SheetBody>
          <EmptyState
            icon={<UserCircle className="h-5 w-5" />}
            title="Not found in this school"
            description="This person isn't in your school's mirrored user list. They may belong to a different tenant, or they haven't logged in yet."
          />
        </SheetBody>
      </>
    );
  }

  const targetHref =
    data.role === "teacher"
      ? `/admin/teachers/${data.id}`
      : data.role === "student"
        ? `/admin/students/${data.id}`
        : null;

  return (
    <>
      <SheetHeader>
        <SheetTitle>{data.full_name}</SheetTitle>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className="truncate">{data.email}</span>
          {data.erp_title && (
            <>
              <span>·</span>
              <ErpTitleBadge title={data.erp_title} />
            </>
          )}
          {!data.erp_title && (
            <>
              <span>·</span>
              <Badge variant="outline" className="capitalize">
                {data.role}
              </Badge>
            </>
          )}
        </div>
      </SheetHeader>
      <SheetBody>
        {targetHref ? (
          <Button
            size="sm"
            onClick={() => {
              onClose();
              router.push(targetHref);
            }}
          >
            Open full profile
            <ArrowRight className="ml-1 h-3.5 w-3.5" />
          </Button>
        ) : (
          <EmptyState
            compact
            title="No drilldown for this role yet"
            description="Only teachers and students have dedicated profile pages right now."
          />
        )}
      </SheetBody>
    </>
  );
}
