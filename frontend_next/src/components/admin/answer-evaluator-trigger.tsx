"use client";

import * as React from "react";
import { ClipboardCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { AnswerEvaluator } from "./answer-evaluator";

/**
 * Trigger button + dialog wrapper for the in-admin Answer Evaluator. Lives
 * in the nav bar / page headers so admins can pop it open from anywhere.
 */
export function AnswerEvaluatorTrigger() {
  const [open, setOpen] = React.useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <ClipboardCheck className="h-4 w-4" /> Evaluate answer
        </Button>
      </DialogTrigger>
      <DialogContent
        className="max-w-4xl"
        description="Score a student answer against the grading rubric. Use manual entry for one-off checks or paste a batch of parsed questions."
      >
        <DialogHeader>
          <DialogTitle>📝 Answer evaluator</DialogTitle>
        </DialogHeader>
        <AnswerEvaluator />
      </DialogContent>
    </Dialog>
  );
}
