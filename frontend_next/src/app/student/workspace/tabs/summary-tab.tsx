"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Volume2, FileText } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { USAGE_QUERY_KEY } from "@/components/dashboard/usage-card";
import type { SummaryResponse } from "@/lib/types";

type SumType = "short" | "detailed" | "both";

function pickSummary(r: SummaryResponse, kind: "short" | "detailed"): string {
  if (kind === "short") return r.short || r.short_summary || r.summary || "";
  return r.detailed || r.detailed_summary || r.summary || "";
}

export function SummaryTab({ pdfId }: { pdfId: string }) {
  const qc = useQueryClient();
  const [topic, setTopic] = React.useState("");
  const [type, setType] = React.useState<SumType>("both");
  const [result, setResult] = React.useState<SummaryResponse | null>(null);
  const [audioFile, setAudioFile] = React.useState<string | null>(null);

  const gen = useMutation({
    mutationFn: () =>
      api.generateSummary({
        pdf_url: pdfId,
        summary_type: type,
        topic: topic.trim() || undefined,
      }),
    onSuccess: (data) => {
      setResult(data);
      setAudioFile(null);
      qc.invalidateQueries({ queryKey: USAGE_QUERY_KEY });
      qc.invalidateQueries({ queryKey: ["history-summaries"] });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  const toAudio = useMutation({
    mutationFn: (text: string) =>
      api.generateAudio({ text, pdf_url: pdfId }),
    onSuccess: (data) => {
      setAudioFile(data.filename);
      toast.success("🔊 Audio ready below.");
      qc.invalidateQueries({ queryKey: USAGE_QUERY_KEY });
      qc.invalidateQueries({ queryKey: ["history-audio"] });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
      <Card>
        <CardContent className="space-y-3 p-5">
          <div>
            <label className="text-xs font-medium text-muted-foreground">
              Topic / focus (optional)
            </label>
            <Textarea
              placeholder="e.g. Summarize chapter 2 · Focus on formulas…"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              rows={2}
            />
          </div>
          <div>
            <p className="text-xs font-medium text-muted-foreground">Length</p>
            <RadioGroup
              value={type}
              onValueChange={(v) => setType(v as SumType)}
              className="mt-1 flex gap-4"
            >
              {(["short", "detailed", "both"] as SumType[]).map((t) => (
                <label key={t} className="flex items-center gap-2 text-sm">
                  <RadioGroupItem value={t} id={`sum-${t}`} />
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </label>
              ))}
            </RadioGroup>
          </div>
          <Button
            onClick={() => gen.mutate()}
            disabled={gen.isPending}
          >
            {gen.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Summarizing…
              </>
            ) : (
              <>
                <FileText className="h-4 w-4" /> Generate summary
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-5 text-sm text-muted-foreground">
          <p className="font-semibold text-foreground">🤖 AI Summarizer</p>
          <p className="mt-1 text-xs">
            Short summaries are perfect for revision; detailed ones double as
            study notes. Tap <em>Convert to audio</em> after generation to get
            a narration.
          </p>
        </CardContent>
      </Card>

      {result && (
        <div className="lg:col-span-2 space-y-4">
          {type === "both" ? (
            <div className="grid gap-3 md:grid-cols-2">
              <SummaryCard
                title="📄 Short summary"
                body={pickSummary(result, "short")}
                onAudio={() =>
                  toAudio.mutate(pickSummary(result, "short"))
                }
                audioPending={toAudio.isPending}
              />
              <SummaryCard
                title="📄 Detailed summary"
                body={pickSummary(result, "detailed")}
                onAudio={() =>
                  toAudio.mutate(pickSummary(result, "detailed"))
                }
                audioPending={toAudio.isPending}
              />
            </div>
          ) : (
            <SummaryCard
              title={
                type === "short"
                  ? "📄 Short summary"
                  : "📄 Detailed summary"
              }
              body={pickSummary(result, type)}
              onAudio={() => toAudio.mutate(pickSummary(result, type))}
              audioPending={toAudio.isPending}
            />
          )}
          {audioFile && (
            <Card>
              <CardContent className="p-4">
                <p className="mb-2 text-xs font-medium text-muted-foreground">
                  🔊 Narration
                </p>
                <audio
                  controls
                  className="w-full"
                  src={`/api/backend/audio/${audioFile}`}
                />
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

function SummaryCard({
  title,
  body,
  onAudio,
  audioPending,
}: {
  title: string;
  body: string;
  onAudio: () => void;
  audioPending: boolean;
}) {
  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-semibold">{title}</h4>
          <Button
            size="sm"
            variant="outline"
            disabled={audioPending || !body}
            onClick={onAudio}
          >
            {audioPending ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Volume2 className="h-3.5 w-3.5" />
            )}
            Convert to audio
          </Button>
        </div>
        <p className="whitespace-pre-wrap text-sm">{body || "(empty)"}</p>
      </CardContent>
    </Card>
  );
}
