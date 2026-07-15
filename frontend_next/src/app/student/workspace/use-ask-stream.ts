"use client";

/**
 * Real Server-Sent-Events streaming for Q&A.
 *
 * POSTs to the backend `/api/ask/stream` endpoint (via the `/api/backend`
 * proxy, which now pipes `text/event-stream` through unbuffered) and surfaces
 * tokens as they arrive. This replaces the old word-by-word "fake stream":
 * words now appear at the speed the model actually produces them.
 *
 * Backend event contract (see backend/main.py:ask_question_stream):
 *     data: {"type": "token", "text": "..."}     # 0..N
 *     data: {"type": "done",  "answer": "...", "sources": [...]}
 *     data: {"type": "error", "detail": "..."}
 *
 * `onToken` receives the FULL accumulated answer each time (not the delta), so
 * the caller can render it directly without tracking concatenation itself.
 * Resolves with the final answer + sources; rejects on an error event or a
 * transport failure so React Query's `onError` can toast as before.
 */
export async function streamAsk(
  params: { pdf_url: string; question: string; session_id: string },
  onToken: (fullText: string) => void,
  signal?: AbortSignal
): Promise<{ answer: string; sources: string[] }> {
  const res = await fetch("/api/backend/ask/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
    signal,
  });

  if (!res.ok || !res.body) {
    // Surface the backend's friendly message when present.
    let detail = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      detail = j?.detail || j?.error || detail;
    } catch {
      /* non-JSON body — keep the status-based message */
    }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let accumulated = "";
  let sources: string[] = [];
  let finalAnswer: string | null = null;

  const handleEvent = (raw: string) => {
    // An SSE event is one or more lines; we only emit `data:` lines.
    const line = raw.split("\n").find((l) => l.startsWith("data:"));
    if (!line) return;
    const json = line.slice(5).trim();
    if (!json) return;
    let evt: { type?: string; text?: string; answer?: string; sources?: string[]; detail?: string };
    try {
      evt = JSON.parse(json);
    } catch {
      return; // ignore malformed chunk rather than killing the stream
    }
    if (evt.type === "token") {
      accumulated += evt.text ?? "";
      onToken(accumulated);
    } else if (evt.type === "done") {
      finalAnswer = evt.answer ?? accumulated;
      sources = evt.sources ?? [];
    } else if (evt.type === "error") {
      throw new Error(evt.detail || "The assistant could not answer.");
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    // SSE events are separated by a blank line.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const chunk = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      handleEvent(chunk);
    }
  }
  // Flush any trailing event without a terminating blank line.
  if (buffer.trim()) handleEvent(buffer);

  return { answer: finalAnswer ?? accumulated, sources };
}
