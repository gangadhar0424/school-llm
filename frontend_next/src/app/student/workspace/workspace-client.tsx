"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  MessageSquare,
  Layers,
  ClipboardList,
  FileText,
  Volume2,
  Video,
  BookOpen,
} from "lucide-react";
import { api } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { QATab } from "./tabs/qa-tab";
import { MultiDocTab } from "./tabs/multi-doc-tab";
import { QuizTab } from "./tabs/quiz-tab";
import { SummaryTab } from "./tabs/summary-tab";
import { AudioTab } from "./tabs/audio-tab";
import { VideoTab } from "./tabs/video-tab";

const TABS = [
  { value: "qa", label: "Q&A", icon: MessageSquare },
  { value: "multi", label: "Multi-Doc", icon: Layers },
  { value: "quiz", label: "Quiz", icon: ClipboardList },
  { value: "summary", label: "Summary", icon: FileText },
  { value: "audio", label: "Audio", icon: Volume2 },
  { value: "video", label: "Video", icon: Video },
] as const;

export function WorkspaceClient({
  initialPdfId,
  initialTab,
}: {
  initialPdfId: string | null;
  initialTab: string;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const [pdfId, setPdfId] = React.useState<string | null>(initialPdfId);
  const [tab, setTab] = React.useState(
    TABS.some((t) => t.value === initialTab) ? initialTab : "qa"
  );
  const [multiPdfIds, setMultiPdfIds] = React.useState<string[]>([]);

  const { data: pdfsData } = useQuery({
    queryKey: ["my-pdfs"],
    queryFn: () => api.myPdfs(100),
  });
  const pdfs = pdfsData?.pdfs ?? [];

  // Sync URL when pdf or tab changes so reload preserves state and the
  // PDF cards on Home can deep-link into specific tabs.
  React.useEffect(() => {
    const next = new URLSearchParams(params.toString());
    if (pdfId) next.set("pdf", pdfId);
    else next.delete("pdf");
    next.set("tab", tab);
    const qs = next.toString();
    const target = qs ? `/student/workspace?${qs}` : "/student/workspace";
    router.replace(target, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdfId, tab]);

  const activePdf = pdfs.find((p) => p.pdf_identifier === pdfId);

  if (pdfs.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
          <BookOpen className="h-10 w-10 text-muted-foreground" />
          <p className="text-sm font-medium">No PDFs yet</p>
          <p className="max-w-md text-xs text-muted-foreground">
            Upload a PDF from the Home tab to unlock the Workspace.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      {/* PDF selector + multi-doc picker */}
      <Card>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-1 flex-col gap-1">
            <label className="text-xs font-medium text-muted-foreground">
              Active PDF
            </label>
            <Select
              value={pdfId ?? ""}
              onValueChange={(v) => setPdfId(v || null)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Pick a PDF" />
              </SelectTrigger>
              <SelectContent>
                {pdfs.map((p) => (
                  <SelectItem
                    key={p.pdf_identifier}
                    value={p.pdf_identifier}
                  >
                    📄 {p.filename}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {activePdf && (
              <p className="text-[10px] text-muted-foreground">
                {activePdf.total_pages} pages · {activePdf.total_chunks} chunks
              </p>
            )}
          </div>
          {pdfs.length >= 2 && (
            <div className="flex flex-1 flex-col gap-1">
              <label className="text-xs font-medium text-muted-foreground">
                Multi-Doc Q&amp;A selection
                <Badge variant="outline" className="ml-2 text-[10px]">
                  {multiPdfIds.length} picked
                </Badge>
              </label>
              <div className="flex max-h-24 flex-wrap gap-1.5 overflow-y-auto rounded-md border border-border bg-surface-2 p-2">
                {pdfs.map((p) => {
                  const checked = multiPdfIds.includes(p.pdf_identifier);
                  return (
                    <button
                      key={p.pdf_identifier}
                      type="button"
                      onClick={() =>
                        setMultiPdfIds((prev) =>
                          prev.includes(p.pdf_identifier)
                            ? prev.filter((x) => x !== p.pdf_identifier)
                            : [...prev, p.pdf_identifier]
                        )
                      }
                      className={cn(
                        "rounded-full border px-2 py-0.5 text-[11px]",
                        checked
                          ? "border-primary bg-primary text-primary-foreground"
                          : "border-border bg-surface text-foreground hover:bg-muted"
                      )}
                    >
                      📄 {p.filename}
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Tabs */}
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="grid grid-cols-3 sm:grid-cols-6">
          {TABS.map((t) => {
            const Icon = t.icon;
            return (
              <TabsTrigger
                key={t.value}
                value={t.value}
                className="gap-1.5"
              >
                <Icon className="h-3.5 w-3.5" />
                <span>{t.label}</span>
              </TabsTrigger>
            );
          })}
        </TabsList>

        <TabsContent value="qa" className="pt-4">
          {pdfId ? (
            <QATab pdfId={pdfId} pdfName={activePdf?.filename || ""} />
          ) : (
            <PickPdfNotice />
          )}
        </TabsContent>
        <TabsContent value="multi" className="pt-4">
          <MultiDocTab pdfIds={multiPdfIds} pdfs={pdfs} />
        </TabsContent>
        <TabsContent value="quiz" className="pt-4">
          {pdfId ? (
            <QuizTab pdfId={pdfId} />
          ) : (
            <PickPdfNotice />
          )}
        </TabsContent>
        <TabsContent value="summary" className="pt-4">
          {pdfId ? <SummaryTab pdfId={pdfId} /> : <PickPdfNotice />}
        </TabsContent>
        <TabsContent value="audio" className="pt-4">
          {pdfId ? (
            <AudioTab pdfId={pdfId} pdfName={activePdf?.filename || ""} />
          ) : (
            <PickPdfNotice />
          )}
        </TabsContent>
        <TabsContent value="video" className="pt-4">
          {pdfId ? <VideoTab pdfId={pdfId} /> : <PickPdfNotice />}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function PickPdfNotice() {
  return (
    <Card>
      <CardContent className="py-10 text-center text-sm text-muted-foreground">
        Pick a PDF above to begin.
      </CardContent>
    </Card>
  );
}
