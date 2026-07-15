"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { format } from "date-fns";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { apiGet } from "@/lib/client-api";

export function AdminAssignmentsClient() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-assignments"],
    queryFn: () => apiGet<{ assignments: any[]; count: number }>("admin/assignments"),
  });

  if (isLoading) {
    return <div className="text-sm text-muted-foreground">Loading assignments...</div>;
  }

  if (error) {
    return (
      <div className="text-sm text-danger">
        Failed to load assignments: {error instanceof Error ? error.message : "Unknown error"}
      </div>
    );
  }

  const assignments = data?.assignments || [];

  if (assignments.length === 0) {
    return (
      <Card className="flex flex-col items-center justify-center p-12 text-center">
        <div className="text-lg font-medium">No assignments found</div>
        <p className="mt-1 text-sm text-muted-foreground">
          Teachers in your school haven't published any assignments yet.
        </p>
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-muted/50 border-b">
            <tr>
              <th className="px-4 py-3 font-medium">Title</th>
              <th className="px-4 py-3 font-medium">Teacher</th>
              <th className="px-4 py-3 font-medium">Class Section</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Submissions</th>
              <th className="px-4 py-3 font-medium">Due Date</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {assignments.map((assignment: any) => (
              <tr key={assignment.id} className="hover:bg-muted/50 transition-colors">
                <td className="px-4 py-3 font-medium">{assignment.title}</td>
                <td className="px-4 py-3 text-muted-foreground">{assignment.teacher_name}</td>
                <td className="px-4 py-3 text-muted-foreground">{assignment.class_section}</td>
                <td className="px-4 py-3">
                  <Badge variant={assignment.status === "published" ? "default" : "secondary"}>
                    {assignment.status}
                  </Badge>
                </td>
                <td className="px-4 py-3">{assignment.submission_count}</td>
                <td className="px-4 py-3 text-muted-foreground">
                  {assignment.due_date ? format(new Date(assignment.due_date), "MMM d, yyyy h:mm a") : "No due date"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
