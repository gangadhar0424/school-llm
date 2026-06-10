"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "@/components/ui/tabs";
import { USAGE_QUERY_KEY } from "@/components/dashboard/usage-card";
import { VoiceChat } from "./voice-chat";

export function AudioTab({
  pdfId,
  pdfName,
}: {
  pdfId: string;
  pdfName: string;
}) {
  return (
    <Tabs defaultValue="voice">
      <TabsList className="grid w-full grid-cols-2 sm:w-auto">
        <TabsTrigger value="voice">🎙️ Voice Chat</TabsTrigger>
        <TabsTrigger value="narrate">📢 Narration</TabsTrigger>
      </TabsList>
      <TabsContent value="voice" className="pt-4">
        <VoiceChat pdfId={pdfId} pdfName={pdfName} />
      </TabsContent>
      <TabsContent value="narrate" className="pt-4">
        <NarrationPanel pdfId={pdfId} />
      </TabsContent>
    </Tabs>
  );
}

function NarrationPanel({ pdfId }: { pdfId: string }) {
  const qc = useQueryClient();
  const [text, setText] = React.useState("");
  const [file, setFile] = React.useState<string | null>(null);

  const gen = useMutation({
    mutationFn: () =>
      api.generateAudio({ text: text.trim(), pdf_url: pdfId }),
    onSuccess: (data) => {
      setFile(data.filename);
      toast.success("🔊 Audio ready.");
      qc.invalidateQueries({ queryKey: USAGE_QUERY_KEY });
      qc.invalidateQueries({ queryKey: ["history-audio"] });
    },
    onError: (e: ApiError) => toast.error(e.message),
  });

  return (
    <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
      <Card>
        <CardContent className="space-y-3 p-5">
          <label className="text-xs font-medium text-muted-foreground">
            Text to narrate
          </label>
          <Textarea
            rows={8}
            placeholder="Paste a summary, definitions, or any text you want narrated…"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <Button onClick={() => gen.mutate()} disabled={!text.trim() || gen.isPending}>
            {gen.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> Generating…
              </>
            ) : (
              <>
                <Volume2 className="h-4 w-4" /> Generate audio
              </>
            )}
          </Button>
          {file && (
            <div className="rounded-md border border-border bg-surface-2 p-3">
              <audio controls className="w-full" src={`/api/backend/audio/${file}`} />
              <a
                href={`/api/backend/audio/${file}`}
                download
                className="mt-2 inline-block text-xs text-primary hover:underline"
              >
                ⬇ Download WAV
              </a>
            </div>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-5 text-sm text-muted-foreground">
          <p className="font-semibold text-foreground">📢 Narration</p>
          <p className="mt-1 text-xs">
            Long text takes a few seconds. The audio file streams back through
            the proxy so the cookie travels — no extra auth required.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
