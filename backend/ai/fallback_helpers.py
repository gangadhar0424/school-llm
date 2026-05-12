"""
Tier 3 fallback helpers — pure-Python, no LLM required.

Activated when BOTH Claude and Ollama are down. Provides degraded-but-functional
answers using classical NLP on the OCR-extracted PDF text.

What works:
  - Q&A: returns the top retrieved RAG chunks as the answer (extractive)
  - Summary: TF-IDF / frequency-based extractive summarization

What does NOT work (returns clear error instead):
  - Quiz / question generation — heuristic quality is too poor to ship.
    Caller should display: "Quiz temporarily unavailable, try Summary or Q&A instead."
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Custom exception so callers can distinguish "LLM down, can't generate" from
# other failures (and the frontend can show a specific friendly message).
# ──────────────────────────────────────────────────────────────────────────────
class AIServiceUnavailable(Exception):
    """Raised when all LLM providers are down AND the requested feature has
    no acceptable Tier 3 fallback (e.g., quiz generation)."""
    def __init__(self, feature: str = "this feature"):
        self.feature = feature
        super().__init__(
            f"AI service is temporarily unavailable for {feature}. "
            f"Please try again in a few minutes."
        )


# ──────────────────────────────────────────────────────────────────────────────
# Detect if an exception means "LLM is down" (vs. a logic bug we should not mask)
# ──────────────────────────────────────────────────────────────────────────────
def is_llm_unavailable(exc: BaseException) -> bool:
    """Best-effort detection of LLM connection/quota/timeout failures.

    Triggers Tier 3 fallback when True. Returns False for programming errors
    (TypeError, KeyError, etc.) so those still surface normally."""
    if exc is None:
        return False
    msg = (str(exc) or "").lower()
    name = type(exc).__name__

    # Network / connection level
    network_markers = (
        "connection", "timeout", "timed out", "max retries", "unreachable",
        "refused", "reset", "broken pipe", "remote disconnected", "dns",
    )
    if any(m in msg for m in network_markers):
        return True

    # HTTP error markers from Anthropic / Ollama
    api_markers = (
        "rate limit", "rate_limit", "quota", "billing", "overloaded",
        "503", "502", "504", "529", "unauthorized", "invalid api key",
        "api error", "anthropic", "ollama", "model not found",
    )
    if any(m in msg for m in api_markers):
        return True

    # Common exception type names from requests / httpx / anthropic SDK
    type_markers = (
        "ConnectionError", "Timeout", "ReadTimeout", "ConnectTimeout",
        "APIError", "APIConnectionError", "APITimeoutError",
        "RateLimitError", "InternalServerError", "ServiceUnavailable",
    )
    if any(m in name for m in type_markers):
        return True

    return False


# ──────────────────────────────────────────────────────────────────────────────
# Question parsing — strip filler, extract real keywords + chapter refs
# ──────────────────────────────────────────────────────────────────────────────
_FILLER_WORDS = frozenset({
    "explain", "explanation", "tell", "me", "about", "what", "is", "are",
    "the", "a", "an", "of", "to", "for", "from", "in", "on", "at", "by",
    "describe", "definition", "define", "give", "show", "please", "can",
    "you", "would", "list", "all", "any", "some", "this", "that", "those",
    "these", "do", "does", "did", "will", "be", "been", "being", "have",
    "has", "had", "with", "and", "or", "but", "so", "if", "when", "where",
    "how", "why", "which", "who", "whom",
})

_CHAPTER_REGEX = re.compile(
    r"\b(?:chapter|chap|ch|lesson|unit|section)\s*[#:\-]?\s*(\d+)",
    re.IGNORECASE,
)


def _extract_keywords(question: str) -> List[str]:
    """Extract real keywords from a question, stripping filler/stopwords."""
    words = re.findall(r"[a-zA-Z]{3,}", (question or "").lower())
    return [w for w in words if w not in _FILLER_WORDS and w not in _STOPWORDS]


def _extract_chapter_refs(question: str) -> List[str]:
    """Find 'chapter N' / 'lesson N' / 'unit N' references → list of numbers."""
    return _CHAPTER_REGEX.findall(question or "")


# ──────────────────────────────────────────────────────────────────────────────
# Chunk quality scoring — separate "real prose" from junk fragments
# ──────────────────────────────────────────────────────────────────────────────
def _chunk_quality_score(text: str) -> float:
    """Score a chunk 0.0–1.0 by how 'prose-like' it is.
    Low scores → tables, math drills, page headers, fragments.
    High scores → narrative sentences with proper structure."""
    if not text or len(text) < 50:
        return 0.0

    # Count letters vs total characters — prose is mostly letters
    letters = sum(1 for c in text if c.isalpha())
    letter_ratio = letters / max(len(text), 1)

    # Count words and sentences
    words = re.findall(r"\b[a-zA-Z]{2,}\b", text)
    word_count = len(words)
    if word_count < 15:
        return 0.0

    # Average word length — too short = abbreviations/labels, too long = OCR errors
    avg_word_len = sum(len(w) for w in words) / max(word_count, 1)
    word_length_score = 1.0 if 4.0 <= avg_word_len <= 7.0 else 0.6

    # Sentence indicators — periods, question marks
    sentence_endings = text.count(".") + text.count("?") + text.count("!")
    sentence_score = min(1.0, sentence_endings / max(word_count / 20, 1))

    # Uppercase ratio — too many caps = section headers / drill tables
    upper_words = sum(1 for w in words if w.isupper() and len(w) > 1)
    upper_ratio = upper_words / max(word_count, 1)
    upper_penalty = 1.0 - min(0.8, upper_ratio * 2.0)

    # Number-heavy text = tables / math drills
    digit_count = sum(1 for c in text if c.isdigit())
    digit_ratio = digit_count / max(len(text), 1)
    digit_penalty = 1.0 - min(0.8, digit_ratio * 3.0)

    # Repetition — "5 TENS 6 UNITS\n5 TENS 7 UNITS" pattern
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    unique_line_starts = len({l[:15].lower() for l in lines}) if lines else 1
    repetition_score = unique_line_starts / max(len(lines), 1) if lines else 1.0

    return (
        letter_ratio * 0.20
        + word_length_score * 0.15
        + sentence_score * 0.20
        + upper_penalty * 0.20
        + digit_penalty * 0.15
        + repetition_score * 0.10
    )


def _keyword_overlap_score(text: str, keywords: List[str]) -> float:
    """Fraction of question keywords that appear in the chunk text."""
    if not keywords:
        return 0.5  # neutral
    text_lower = text.lower()
    hits = sum(1 for kw in keywords if kw in text_lower)
    return hits / len(keywords)


def _filter_and_rerank_chunks(
    chunks: List[Dict],
    question: str,
    min_quality: float = 0.35,
    max_chunks: int = 3,
) -> List[Dict]:
    """Quality-filter and re-rank chunks for extractive Q&A.

    Strategy:
      1. Drop junk chunks (low prose quality)
      2. Boost chunks that match question keywords
      3. Boost chunks that match referenced chapters
      4. Return top-N by combined score
    """
    if not chunks:
        return []

    keywords = _extract_keywords(question)
    chapter_refs = set(_extract_chapter_refs(question))

    scored: List[tuple] = []
    for ch in chunks:
        text = (ch.get("text") or ch.get("content") or "").strip()
        meta = ch.get("metadata") or {}

        quality = _chunk_quality_score(text)
        # Drop obvious junk early
        if quality < min_quality:
            continue

        keyword_score = _keyword_overlap_score(text, keywords)

        # Chapter match bonus — strong signal when user asked about Chapter N
        chapter_bonus = 0.0
        if chapter_refs:
            chunk_chapter = str(meta.get("chapter") or "").strip()
            section_code = str(meta.get("section_code") or "").strip()
            if chunk_chapter in chapter_refs:
                chapter_bonus = 0.5
            elif any(section_code.startswith(f"{c}.") for c in chapter_refs):
                chapter_bonus = 0.4

        # Combined score: weighted blend
        combined = (
            quality * 0.40
            + keyword_score * 0.45
            + chapter_bonus * 0.40  # additive bonus, not capped at 1
        )
        scored.append((combined, ch))

    if not scored:
        # All chunks were filtered out — fall back to original top results
        # but still cap by max_chunks
        return chunks[:max_chunks]

    scored.sort(key=lambda t: t[0], reverse=True)
    return [c for _, c in scored[:max_chunks]]


def _merge_consecutive_chunks(chunks: List[Dict]) -> List[Dict]:
    """If multiple top chunks come from the same page, merge them so the
    user sees a coherent passage instead of fragmented snippets."""
    if len(chunks) <= 1:
        return chunks

    merged: List[Dict] = []
    by_page: Dict[int, Dict] = {}
    for ch in chunks:
        meta = ch.get("metadata") or {}
        page = meta.get("page_number") or meta.get("page")
        if page is None:
            merged.append(ch)
            continue
        if page in by_page:
            existing_text = by_page[page].get("text", "")
            new_text = ch.get("text", "")
            if new_text not in existing_text:
                by_page[page]["text"] = existing_text + "\n\n" + new_text
        else:
            by_page[page] = dict(ch)
            by_page[page]["text"] = ch.get("text", "")
            merged.append(by_page[page])
    return merged


# ──────────────────────────────────────────────────────────────────────────────
# Extractive Q&A — return RAG chunks formatted as the answer
# ──────────────────────────────────────────────────────────────────────────────
def build_extractive_qa_answer(
    question: str,
    chunks: List[Dict],
    max_chunks: int = 3,
) -> Dict:
    """Format vector-retrieved chunks as a 'best-effort' answer when no LLM
    is available. Quality-filters and re-ranks to surface real prose over
    drill tables / page headers / fragments."""
    if not chunks:
        return {
            "answer": (
                "⚠️ AI is temporarily unavailable and no relevant passages "
                "could be retrieved from the document. Please try again later."
            ),
            "sources": [],
            "fallback_mode": "extractive",
            "degraded": True,
        }

    # 1. Quality-filter + re-rank by keyword & chapter relevance
    filtered = _filter_and_rerank_chunks(chunks, question, max_chunks=max_chunks * 2)
    # 2. Merge multiple chunks from the same page so the answer reads as a passage
    filtered = _merge_consecutive_chunks(filtered)
    top = filtered[:max_chunks]

    if not top:
        # Quality filter rejected everything — original chunks were all junk
        return {
            "answer": (
                "⚠️ **Offline mode** — AI assistant is temporarily unavailable, "
                "and no clean prose passages could be found in the document "
                f"for _\"{question.strip()}\"_.\n\n"
                "Try rephrasing your question with more specific terms "
                "(e.g., the topic name, a key concept, or a specific section)."
            ),
            "sources": [],
            "fallback_mode": "extractive",
            "degraded": True,
        }

    header = (
        f"⚠️ **Offline mode** — AI assistant is temporarily unavailable. "
        f"Here are the most relevant passages from your document for "
        f"_\"{question.strip()}\"_:\n\n"
    )

    body_parts: List[str] = []
    sources: List[Dict] = []
    for i, ch in enumerate(top, start=1):
        text = (ch.get("text") or ch.get("content") or "").strip()
        meta = ch.get("metadata") or {}
        page = meta.get("page_number") or meta.get("page") or "?"
        section = meta.get("section_title") or meta.get("section") or ""
        section_str = f" · _{section}_" if section else ""

        # Trim leading/trailing whitespace lines for cleaner display
        text = "\n".join(line for line in text.splitlines() if line.strip())

        body_parts.append(f"**Passage {i}** (page {page}{section_str})\n\n{text}")
        sources.append({
            "page": page,
            "section": section,
            "snippet": text[:200] + ("…" if len(text) > 200 else ""),
        })

    answer = header + "\n\n---\n\n".join(body_parts)
    answer += (
        "\n\n---\n_💡 Try again in a few minutes for a synthesized AI answer._"
    )

    return {
        "answer": answer,
        "sources": sources,
        "fallback_mode": "extractive",
        "degraded": True,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Extractive Summary — frequency-weighted sentence ranking
# ──────────────────────────────────────────────────────────────────────────────
_STOPWORDS = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an",
    "and", "any", "are", "as", "at", "be", "because", "been", "before",
    "being", "below", "between", "both", "but", "by", "could", "did",
    "do", "does", "doing", "down", "during", "each", "few", "for", "from",
    "further", "had", "has", "have", "having", "he", "her", "here", "hers",
    "him", "his", "how", "i", "if", "in", "into", "is", "it", "its",
    "itself", "me", "more", "most", "my", "myself", "no", "nor", "not",
    "now", "of", "off", "on", "once", "only", "or", "other", "our",
    "ours", "out", "over", "own", "same", "she", "should", "so", "some",
    "such", "than", "that", "the", "their", "theirs", "them", "then",
    "there", "these", "they", "this", "those", "through", "to", "too",
    "under", "until", "up", "very", "was", "we", "were", "what", "when",
    "where", "which", "while", "who", "whom", "why", "will", "with",
    "would", "you", "your", "yours",
})


def _split_sentences(text: str) -> List[str]:
    """Lightweight sentence splitter. Avoids dragging in nltk/spacy as a
    dependency — for Tier 3 we accept slightly imperfect splits."""
    # Normalize whitespace and remove obvious junk
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    # Split on sentence-final punctuation followed by space + capital letter
    raw = re.split(r"(?<=[.!?])\s+(?=[A-Z\"‘“])", text)
    sentences = [s.strip() for s in raw if 30 < len(s.strip()) < 500]
    return sentences


def _word_frequencies(text: str) -> Counter:
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    return Counter(w for w in words if w not in _STOPWORDS)


def build_extractive_summary(
    text: str,
    num_sentences: int = 7,
    style: str = "short",
) -> str:
    """Pick the top N highest-scoring sentences via frequency-weighted scoring.

    Style: 'short' → ~5 sentences, 'detailed' → ~12 sentences.
    Output preserves original sentence order for readability.
    """
    if not text or not text.strip():
        return (
            "⚠️ AI is temporarily unavailable and no document text could be "
            "summarized. Please try again later."
        )

    sentences = _split_sentences(text)
    if len(sentences) <= num_sentences:
        # Document is too short — just return everything
        return " ".join(sentences) if sentences else text[:500]

    if style == "detailed":
        num_sentences = max(num_sentences, 12)
    else:
        num_sentences = min(num_sentences, 7)

    freqs = _word_frequencies(text)
    if not freqs:
        return " ".join(sentences[:num_sentences])

    max_freq = max(freqs.values()) or 1
    normalized = {w: c / max_freq for w, c in freqs.items()}

    # Score sentences: sum of normalized word frequencies, length-normalized
    scored: List[tuple] = []
    for idx, sentence in enumerate(sentences):
        words = re.findall(r"[a-zA-Z]{3,}", sentence.lower())
        if not words:
            continue
        # Bonus for sentences early in the document (often topical / intro)
        position_bonus = max(0.0, 1.0 - (idx / len(sentences))) * 0.3
        # Penalty for very long sentences
        length_factor = 1.0 / math.sqrt(max(len(words), 1))

        score = sum(normalized.get(w, 0.0) for w in words) * length_factor
        score += position_bonus
        scored.append((idx, score, sentence))

    # Pick top-scoring, then sort by original position for readability
    scored.sort(key=lambda t: t[1], reverse=True)
    chosen = sorted(scored[:num_sentences], key=lambda t: t[0])

    header = (
        "⚠️ **Offline mode** — AI assistant is temporarily unavailable. "
        "Here is an extractive summary built from the document's key sentences:\n\n"
    )
    body = " ".join(s for _, _, s in chosen)
    footer = "\n\n_💡 Try again in a few minutes for an AI-generated summary._"

    return header + body + footer
