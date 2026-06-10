"use client";

import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Mic, MicOff, Square, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/client-api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { USAGE_QUERY_KEY } from "@/components/dashboard/usage-card";
import { cn } from "@/lib/utils";

/**
 * Voice Chat — three steps, no backend STT round-trip:
 *
 *   1. Click 🎙️ → start browser SpeechRecognition (Web Speech API).
 *   2. Recognized text → POST /api/ask with the active PDF.
 *   3. Answer → POST /api/audio (TTS) → autoplay the resulting WAV.
 *
 * Voice Chat consumes BOTH the qa and audio quotas per turn since under
 * the hood it's just Q&A + TTS chained together.
 *
 * Browser support: Chrome, Edge, Safari (via webkitSpeechRecognition).
 * Firefox doesn't ship SpeechRecognition; users there see a clear
 * fallback message and can still use the Narration tab.
 */

interface VoiceTurn {
  role: "user" | "assistant";
  content: string;
  audioFile?: string;
  autoplay?: boolean;
}

// Minimal SpeechRecognition typings — the Web Speech API isn't in the
// default lib.dom yet. Keep these private to this component.
interface SpeechRecognitionResultLike {
  isFinal: boolean;
  [index: number]: { transcript: string };
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionInstance extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: ((e: Event & { error?: string }) => void) | null;
  onend: (() => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionInstance;

function getSpeechRecognition(): SpeechRecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export function VoiceChat({
  pdfId,
  pdfName,
}: {
  pdfId: string;
  pdfName: string;
}) {
  const qc = useQueryClient();
  const [turns, setTurns] = React.useState<VoiceTurn[]>([]);
  const [listening, setListening] = React.useState(false);
  const [interim, setInterim] = React.useState("");
  const recognitionRef = React.useRef<SpeechRecognitionInstance | null>(null);
  const finalTranscriptRef = React.useRef("");
  const supported = React.useMemo(() => getSpeechRecognition() !== null, []);

  // Ask → TTS pipeline. One mutation handles both calls so the UI shows
  // a single pending state until the audio is ready to play.
  const turn = useMutation({
    mutationFn: async (spoken: string) => {
      // Last 6 messages of short-term context — enough for follow-ups
      // ("now explain it simpler") without blowing the token budget on
      // every turn.
      const history = turns.slice(-6).map((t) => ({
        role: t.role,
        content: t.content,
      }));
      const res = await api.ask({
        pdf_url: pdfId,
        question: spoken,
        conversation_history: history,
      });
      const audio = await api.generateAudio({
        text: res.answer,
        pdf_url: pdfId,
      });
      return { answer: res.answer, audioFile: audio.filename };
    },
    onSuccess: ({ answer, audioFile }) => {
      setTurns((prev) => {
        // Mark all prior assistant audios as no-autoplay so only the
        // latest one auto-starts.
        const reset = prev.map((t) => ({ ...t, autoplay: false }));
        return [
          ...reset,
          {
            role: "assistant" as const,
            content: answer,
            audioFile,
            autoplay: true,
          },
        ];
      });
      qc.invalidateQueries({ queryKey: USAGE_QUERY_KEY });
    },
    onError: (e: ApiError) => {
      toast.error(e.message);
      // Drop the orphaned user turn so the user can retry cleanly.
      setTurns((prev) => prev.slice(0, -1));
    },
  });

  const stopListening = React.useCallback(() => {
    const rec = recognitionRef.current;
    if (!rec) return;
    try {
      rec.stop();
    } catch {
      /* already stopped */
    }
  }, []);

  const handleResult = React.useCallback(
    (event: SpeechRecognitionEventLike) => {
      let interimText = "";
      let finalChunk = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        const transcript = r[0]?.transcript ?? "";
        if (r.isFinal) finalChunk += transcript;
        else interimText += transcript;
      }
      if (finalChunk) finalTranscriptRef.current += finalChunk;
      setInterim(interimText);
    },
    []
  );

  const startListening = () => {
    const Ctor = getSpeechRecognition();
    if (!Ctor) {
      toast.error("Your browser doesn't support speech recognition.");
      return;
    }
    if (turn.isPending) return;

    const rec = new Ctor();
    rec.lang = "en-US";
    rec.continuous = false; // Stop automatically on a pause — matches the
    //                         "single-utterance" mic-recorder UX.
    rec.interimResults = true;
    finalTranscriptRef.current = "";
    setInterim("");

    rec.onresult = handleResult;
    rec.onerror = (e) => {
      const code = (e as Event & { error?: string }).error || "";
      if (code !== "aborted" && code !== "no-speech") {
        toast.error(`Mic error: ${code || "unknown"}`);
      }
    };
    rec.onend = () => {
      setListening(false);
      const text = finalTranscriptRef.current.trim();
      setInterim("");
      recognitionRef.current = null;
      if (!text) return;
      // Append the user turn optimistically, then fire the mutation.
      setTurns((prev) => [
        ...prev.map((t) => ({ ...t, autoplay: false })),
        { role: "user", content: text },
      ]);
      turn.mutate(text);
    };

    recognitionRef.current = rec;
    setListening(true);
    try {
      rec.start();
    } catch {
      setListening(false);
      toast.error("Could not start mic. Check browser permissions.");
    }
  };

  // Make sure the recognition object is shut down if the component
  // unmounts mid-listen.
  React.useEffect(() => {
    return () => {
      const rec = recognitionRef.current;
      if (rec) {
        try {
          rec.abort();
        } catch {
          /* ignore */
        }
      }
    };
  }, []);

  if (!supported) {
    return (
      <Card>
        <CardContent className="space-y-2 p-5 text-sm">
          <p className="font-medium text-foreground">
            Voice Chat needs a browser with the Web Speech API.
          </p>
          <p className="text-xs text-muted-foreground">
            Chrome, Edge, and Safari support it. Firefox doesn&apos;t yet — try
            the Narration sub-tab instead, which works on every browser.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold">
              🎙️ Voice Chat — grounded on{" "}
              <span className="text-foreground">{pdfName}</span>
            </p>
            <p className="text-xs text-muted-foreground">
              Tap mic, ask a question, and the answer plays back automatically.
              Each turn consumes one Q&amp;A and one Audio credit.
            </p>
          </div>
          {turns.length > 0 && (
            <Button
              size="sm"
              variant="ghost"
              className="text-danger hover:bg-danger/10"
              onClick={() => setTurns([])}
            >
              <Trash2 className="h-3.5 w-3.5" />
              New conversation
            </Button>
          )}
        </div>

        <div className="max-h-[55vh] space-y-2 overflow-y-auto rounded-md border border-border bg-surface-2 p-3">
          {turns.length === 0 && !turn.isPending && (
            <p className="py-8 text-center text-xs text-muted-foreground">
              Press the mic below and ask anything about the PDF.
            </p>
          )}
          {turns.map((t, i) => (
            <Turn key={i} turn={t} />
          ))}
          {turn.isPending && (
            <div className="flex items-center gap-2 rounded-md bg-surface px-3 py-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Thinking and generating audio…
            </div>
          )}
        </div>

        {interim && (
          <div className="rounded-md border border-dashed border-primary/40 bg-primary-chip px-3 py-2 text-xs text-muted-foreground">
            <span className="mr-2 font-semibold text-foreground">Hearing:</span>
            {interim}
          </div>
        )}

        <div className="flex items-center justify-center gap-3">
          {!listening ? (
            <Button
              size="lg"
              onClick={startListening}
              disabled={turn.isPending}
              className="rounded-full px-6"
            >
              <Mic className="h-5 w-5" />
              {turn.isPending ? "Working…" : "Tap to speak"}
            </Button>
          ) : (
            <Button
              size="lg"
              variant="danger"
              onClick={stopListening}
              className="rounded-full px-6"
            >
              <Square className="h-4 w-4" />
              Stop
            </Button>
          )}
          {listening && (
            <span className="flex items-center gap-1 text-xs text-danger">
              <span className="inline-block h-2 w-2 animate-ping rounded-full bg-danger" />
              Listening…
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function Turn({ turn }: { turn: VoiceTurn }) {
  return (
    <div
      className={cn(
        "flex",
        turn.role === "user" ? "justify-end" : "justify-start"
      )}
    >
      <div
        className={cn(
          "max-w-[85%] rounded-lg px-3 py-2 text-sm",
          turn.role === "user"
            ? "bg-primary text-primary-foreground"
            : "bg-surface text-foreground"
        )}
      >
        {turn.role === "user" ? (
          <div className="flex items-center gap-1.5">
            <MicOff className="h-3 w-3 opacity-70" />
            <span className="whitespace-pre-wrap">{turn.content}</span>
          </div>
        ) : (
          <>
            <p className="whitespace-pre-wrap">{turn.content}</p>
            {turn.audioFile && (
              <audio
                controls
                autoPlay={turn.autoplay}
                className="mt-2 h-8 w-full"
                src={`/api/backend/audio/${turn.audioFile}`}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
