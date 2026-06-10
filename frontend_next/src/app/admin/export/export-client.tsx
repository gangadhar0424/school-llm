"use client";

import * as React from "react";
import { Download } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

export function ExportClient() {
  const [email, setEmail] = React.useState("");
  const [start, setStart] = React.useState("");
  const [end, setEnd] = React.useState("");

  const href = React.useMemo(() => {
    const url = new URL("/api/backend/admin/export-logs", window.location.origin);
    if (email) url.searchParams.set("user_email", email);
    if (start) url.searchParams.set("start_date", start);
    if (end) url.searchParams.set("end_date", end);
    return url.toString();
  }, [email, start, end]);

  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <p className="text-sm text-muted-foreground">
          Download all (or filtered) activity logs as a CSV. Filters are
          inclusive; leave blank for all rows.
        </p>
        <div>
          <Label>User email (optional)</Label>
          <Input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="someone@example.com"
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Start date</Label>
            <Input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
          </div>
          <div>
            <Label>End date</Label>
            <Input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </div>
        </div>
        <Button asChild>
          <a href={href} download>
            <Download className="h-4 w-4" /> Download CSV
          </a>
        </Button>
      </CardContent>
    </Card>
  );
}
