"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Video as VideoIcon } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { USAGE_QUERY_KEY } from "@/components/dashboard/usage-card";

export function VideoTab({ pdfId }: { pdfId: string }) {
  const qc = useQueryClient();
  const [query, setQuery] = React.useState("");
  const [style, setStyle] = React.useState<"slides" | "manim">("slides");
  const [file, setFile] = React.useState<string | null>(null);

  const gen = useMutation({
    mutationFn: () =>
      api.generateVideo({
        pdf_url: pdfId,
        query: query.trim() || undefined,
        style,
      }),
    onSuccess: (data) => {
      setFile(data.filename);
      toast.success("🎬 Video ready.");
      qc.invalidateQueries({ queryKey: USAGE_QUERY_KEY });
      qc.invalidateQueries({ queryKey: ["history-video"] });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
      <Card>
        <CardContent className="space-y-3 p-5">
          <label className="text-xs font-medium text-muted-foreground">
            What should this video cover?
          </label>
          <Textarea
            rows={3}
            placeholder="e.g. Explain photosynthesis at a Class 5 level"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div>
            <p className="text-xs font-medium text-muted-foreground">Style</p>
            <RadioGroup
              value={style}
              onValueChange={(v) => setStyle(v as "slides" | "manim")}
              className="mt-1 flex gap-4"
            >
              <label className="flex items-center gap-2 text-sm">
                <RadioGroupItem value="slides" id="vid-slides" />
                Animated slides
              </label>
              <label className="flex items-center gap-2 text-sm">
                <RadioGroupItem value="manim" id="vid-manim" />
                Manim animations
              </label>
            </RadioGroup>
          </div>
          <Button onClick={() => gen.mutate()} disabled={gen.isPending}>
            {gen.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Rendering (may take
                a couple minutes)…
              </>
            ) : (
              <>
                <VideoIcon className="h-4 w-4" /> Generate video
              </>
            )}
          </Button>
          {file && (
            <div className="rounded-md border border-border bg-surface-2 p-3">
              <video
                controls
                className="w-full rounded-md"
                src={`/api/backend/video/${file}`}
              />
              <a
                href={`/api/backend/video/${file}`}
                download
                className="mt-2 inline-block text-xs text-primary hover:underline"
              >
                ⬇ Download MP4
              </a>
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-5 text-sm text-muted-foreground">
          <p className="font-semibold text-foreground">🎬 Video generator</p>
          <p className="mt-1 text-xs">
            Renders a short animated video grounded on the active PDF. Manim
            takes longer but produces math-style animations.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
