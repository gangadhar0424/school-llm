"use client";

import * as React from "react";

/**
 * Word-by-word "fake stream" of a full string. /api/ask returns the answer
 * as one JSON blob; we animate it word-by-word (~18 ms per word) so the
 * UI feels alive while the user reads.
 *
 * Real SSE streaming is on the roadmap; switching this hook to read an
 * `EventSource` will be a drop-in replacement.
 *
 * Implementation note: React 19's lint forbids both `setState` in effect
 * bodies AND ref-access during render. We therefore use the canonical
 * "tracked-prop state" pattern (a second piece of state holds the last
 * `full` we saw; comparing it during render is allowed and re-rendering
 * once is the React-docs-recommended derivation idiom).
 */
export function useFakeStream(full: string | null | undefined, wordMs = 18) {
  const [text, setText] = React.useState("");
  const [done, setDone] = React.useState(true);
  const [tracked, setTracked] = React.useState<string | null | undefined>(full);

  if (tracked !== full) {
    setTracked(full);
    setText("");
    setDone(!full);
  }

  React.useEffect(() => {
    if (!full) return;
    const words = full.split(/(\s+)/);
    let i = 0;
    const id = setInterval(() => {
      i += 1;
      setText(words.slice(0, i).join(""));
      if (i >= words.length) {
        clearInterval(id);
        setDone(true);
      }
    }, wordMs);
    return () => clearInterval(id);
  }, [full, wordMs]);

  return { text, done };
}
