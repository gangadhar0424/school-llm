"use client";

import { ChatPanel } from "./qa-tab";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/client-api";
import type { PdfItem } from "@/lib/types";

export function MultiDocTab({
  pdfIds,
  pdfs,
}: {
  pdfIds: string[];
  pdfs: PdfItem[];
}) {
  if (pdfIds.length < 2) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          Pick at least <strong>2 PDFs</strong> using the chips at the top to
          query across multiple documents.
        </CardContent>
      </Card>
    );
  }

  const names = pdfs
    .filter((p) => pdfIds.includes(p.pdf_identifier))
    .map((p) => p.filename);

  return (
    <ChatPanel
      mode="multi"
      pdfIds={pdfIds}
      header={
        <>
          🔀 <strong>Multi-Doc</strong> · Querying across{" "}
          <span className="text-foreground">{pdfIds.length}</span> documents:{" "}
          {names.slice(0, 3).join(", ")}
          {names.length > 3 ? ", …" : ""}
        </>
      }
      ask={(question, sessionId) =>
        api.askMulti({
          pdf_identifiers: pdfIds,
          question,
          session_id: sessionId,
        })
      }
    />
  );
}
