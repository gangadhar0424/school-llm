"""
AI Summary Generation Module
Creates short and detailed summaries using Ollama
"""
import logging
import json
import re
import time
from typing import Dict
from config import settings
from ai.ollama_client import ollama_client, check_llm_availability
from ai.llm_client import get_llm_client
from ai.fallback_helpers import is_llm_unavailable, build_extractive_summary
from timing_utils import log_phase

logger = logging.getLogger(__name__)


def _trim_to_last_sentence(text: str) -> str:
    """Backstop against mid-sentence cutoffs caused by hitting max_tokens.
    If the model's output ends without sentence-ending punctuation (`.`, `!`,
    `?`, `:`), find the last complete sentence and trim back to it. This
    ensures the student never sees a dangling clause like
    'literature can be used as a tool to'."""
    if not text:
        return text
    s = text.rstrip()
    if not s:
        return text
    # If it already ends cleanly, return as-is.
    if s[-1] in {".", "!", "?", "…", "”", '"', "'", ")", "]"}:
        return s
    # Find the last sentence terminator and trim there.
    last_terminator = max(
        s.rfind("."),
        s.rfind("!"),
        s.rfind("?"),
        s.rfind("…"),
    )
    if last_terminator <= 0:
        # No sentence boundary found at all — return as-is rather than
        # nuking everything.
        return s
    # Keep everything up to and including the terminator.
    return s[: last_terminator + 1].rstrip()


class SummaryGenerator:
    """Generate summaries from PDF text using Ollama"""
    
    def __init__(self):
        """Initialize model settings"""
        self.model = settings.OLLAMA_CHAT_MODEL

    def _representative_text(self, text: str, max_chars: int) -> str:
        """Sample start/middle/end segments for better whole-document coverage."""
        if len(text) <= max_chars:
            return text

        # Include more from the beginning to capture titles/contents.
        part = max_chars // 3
        start = text[:part]

        mid_start = max((len(text) // 2) - (part // 2), 0)
        middle = text[mid_start:mid_start + part]

        end = text[-part:]
        return (start + "\n\n" + middle + "\n\n" + end).strip()

    def _prepare_input(self, text: str, study_context: str, max_chars: int) -> str:
        """Prefer the cached compact study context when available."""
        candidate = (study_context or "").strip()
        if candidate:
            return candidate[:max_chars]
        return self._representative_text(text, max_chars)

    def _parse_summary_bundle(self, content: str) -> Dict[str, str]:
        """Parse bundled summary JSON with a light fallback."""
        cleaned = (content or "").strip()

        if "```" in cleaned:
            parts = cleaned.split("```")
            for part in parts:
                candidate = part.strip()
                if candidate.lower().startswith("json"):
                    candidate = candidate[4:].strip()
                if candidate.startswith("{"):
                    cleaned = candidate
                    break

        try:
            data = json.loads(cleaned)
            if isinstance(data, dict):
                return {
                    "short_summary": str(data.get("short_summary", "")).strip(),
                    "detailed_summary": str(data.get("detailed_summary", "")).strip(),
                }
        except Exception:
            pass

        short_match = re.search(r"short_summary\s*[:=]\s*(.+?)(?:\n\s*detailed_summary\s*[:=]|$)", cleaned, re.I | re.S)
        detailed_match = re.search(r"detailed_summary\s*[:=]\s*(.+)$", cleaned, re.I | re.S)

        return {
            "short_summary": short_match.group(1).strip() if short_match else "",
            "detailed_summary": detailed_match.group(1).strip() if detailed_match else "",
        }
    
    def _topic_instruction(self, topic: str = None) -> str:
        """Return a topic-focused instruction to inject into the system prompt."""
        if not topic:
            return ""
        return f" Focus ONLY on the topic: '{topic}'. If this topic is not present, summarize what IS present related to it."

    async def generate_short_summary(self, text: str, study_context: str = "", topic: str = None) -> str:
        """Generate a concise summary (2-3 paragraphs), optionally focused on a topic."""
        try:
            total_started = time.perf_counter()
            phase_started = time.perf_counter()
            source_text = self._prepare_input(text, study_context, max_chars=6000)
            log_phase(
                logger,
                "summary.short",
                "prepare_input",
                phase_started,
                source_chars=len(source_text),
                used_study_context=bool((study_context or "").strip()),
                topic=topic or "",
            )

            topic_hint = self._topic_instruction(topic)
            phase_started = time.perf_counter()

            # Pre-flight: skip LLM call if no provider is reachable
            if not check_llm_availability()["any"]:
                logger.info("Short summary skipping LLM — using extractive fallback")
                return build_extractive_summary(source_text, num_sentences=5, style="short")

            try:
                _llm = get_llm_client()
                summary = await _llm.chat(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are writing a SHORT summary of a school PDF for a student. "
                                "ADAPT THE STRUCTURE to what the source actually is — first decide which one it looks like:\n"
                                "  • Multi-chapter TEXTBOOK (multiple distinct chapters/topics) → bullet list, ONE sentence per chapter, naming each chapter\n"
                                "  • Single-topic explainer (one science concept, one math chapter, one story) → 2-3 short paragraphs covering the key ideas\n"
                                "  • Notes / mixed material / exam paper → 2-3 paragraphs organised by theme\n\n"
                                f"{topic_hint}"
                                "Hard rules:\n"
                                "  1. Preserve chapter names, topic names, and proper nouns exactly as they appear in the source.\n"
                                "  2. Keep the entire summary brief — at most ~350 words.\n"
                                "  3. CRITICAL: always finish on a complete sentence. If you are approaching the length limit, stop at the next sentence boundary and do not start a new thought. Never leave a sentence half-finished."
                            )
                        },
                        {"role": "user", "content": source_text}
                    ],
                    model=_llm.generation_model or self.model,
                    temperature=0.2,
                    max_tokens=600,
                )
                # Trim any trailing dangling clause (no punctuation at the end).
                summary = _trim_to_last_sentence(summary)
            except Exception as llm_exc:
                if is_llm_unavailable(llm_exc):
                    logger.error(
                        "Both LLM providers unavailable in short summary — using extractive fallback: %s",
                        llm_exc,
                    )
                    return build_extractive_summary(source_text, num_sentences=5, style="short")
                raise
            log_phase(
                logger,
                "summary.short",
                "llm_generate",
                phase_started,
                output_chars=len(summary or ""),
            )
            log_phase(logger, "summary.short", "total", total_started)
            logger.info("Generated short summary")
            return summary

        except Exception as e:
            logger.error(f"Error generating short summary: {e}")
            raise Exception(f"Failed to generate summary: {str(e)}")
    
    async def generate_detailed_summary(self, text: str, study_context: str = "", topic: str = None) -> str:
        """Generate a comprehensive detailed summary, optionally focused on a topic."""
        try:
            total_started = time.perf_counter()
            phase_started = time.perf_counter()
            source_text = self._prepare_input(text, study_context, max_chars=8000)
            log_phase(
                logger,
                "summary.detailed",
                "prepare_input",
                phase_started,
                source_chars=len(source_text),
                used_study_context=bool((study_context or "").strip()),
                topic=topic or "",
            )

            topic_hint = self._topic_instruction(topic)
            phase_started = time.perf_counter()

            # Pre-flight: skip LLM call if no provider is reachable
            if not check_llm_availability()["any"]:
                logger.info("Detailed summary skipping LLM — using extractive fallback")
                return build_extractive_summary(source_text, num_sentences=12, style="detailed")

            try:
                _llm = get_llm_client()
                summary = await _llm.chat(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are writing a DETAILED study summary of a school PDF for a student. "
                                "ADAPT THE STRUCTURE to what the source is:\n"
                                "  • Multi-chapter TEXTBOOK → bullet list, ONE short paragraph (2-3 sentences) per chapter, each starting with the chapter name\n"
                                "  • Single-topic explainer → ### headed sections (Definitions, Key Ideas, Worked Example, etc.) with bullet points under each\n"
                                "  • Notes / mixed material → organise by theme with sub-bullets\n\n"
                                f"{topic_hint}"
                                "Hard rules:\n"
                                "  1. Preserve every chapter name, formula, technical term, and proper noun exactly as in the source.\n"
                                "  2. Use markdown bullets / headings for structure.\n"
                                "  3. Aim for ~600-700 words. Do not pad.\n"
                                "  4. CRITICAL: always end on a complete sentence. If you're nearing the length limit, finish your current point at its next natural sentence break and stop — do NOT begin a new bullet or sentence you can't complete."
                            )
                        },
                        {"role": "user", "content": source_text}
                    ],
                    model=_llm.generation_model or self.model,
                    temperature=0.2,
                    max_tokens=1100,
                )
                summary = _trim_to_last_sentence(summary)
            except Exception as llm_exc:
                if is_llm_unavailable(llm_exc):
                    logger.error(
                        "Both LLM providers unavailable in detailed summary — using extractive fallback: %s",
                        llm_exc,
                    )
                    return build_extractive_summary(source_text, num_sentences=12, style="detailed")
                raise
            log_phase(
                logger,
                "summary.detailed",
                "llm_generate",
                phase_started,
                output_chars=len(summary or ""),
            )
            log_phase(logger, "summary.detailed", "total", total_started)
            logger.info("Generated detailed summary")
            return summary

        except Exception as e:
            logger.error(f"Error generating detailed summary: {e}")
            raise Exception(f"Failed to generate detailed summary: {str(e)}")
    
    async def generate_both_summaries(self, text: str, study_context: str = "", topic: str = None) -> Dict[str, str]:
        """
        Generate both summary variants in a single model call.
        This is faster on local Ollama setups than running two separate chats.
        """
        try:
            total_started = time.perf_counter()
            phase_started = time.perf_counter()
            source_text = self._prepare_input(text, study_context, max_chars=7000)
            log_phase(
                logger,
                "summary.both",
                "prepare_input",
                phase_started,
                source_chars=len(source_text),
                used_study_context=bool((study_context or "").strip()),
            )
            topic_hint = self._topic_instruction(topic)
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Return ONLY valid JSON with exactly two string fields: "
                        "short_summary and detailed_summary. "
                        "The short summary must be 2-3 concise paragraphs. "
                        "The detailed summary must use 6-8 compact bullet points. "
                        f"Preserve exact chapter/topic names when present.{topic_hint}"
                    )
                },
                {"role": "user", "content": source_text}
            ]

            try:
                phase_started = time.perf_counter()
                _llm = get_llm_client()
                content = await _llm.chat(
                    messages=messages,
                    model=_llm.generation_model or self.model,
                    temperature=0.2,
                    max_tokens=460,
                    response_format="json",
                )
                log_phase(
                    logger,
                    "summary.both",
                    "llm_generate_json",
                    phase_started,
                    output_chars=len(content or ""),
                )
            except Exception as exc:
                logger.warning("Bundled summary JSON mode failed; retrying without explicit JSON mode: %s", exc)
                phase_started = time.perf_counter()
                _llm = get_llm_client()
                content = await _llm.chat(
                    messages=messages,
                    model=_llm.generation_model or self.model,
                    temperature=0.2,
                    max_tokens=460,
                )
                log_phase(
                    logger,
                    "summary.both",
                    "llm_generate_fallback",
                    phase_started,
                    output_chars=len(content or ""),
                )

            phase_started = time.perf_counter()
            summaries = self._parse_summary_bundle(content)
            log_phase(logger, "summary.both", "parse_bundle", phase_started)
            short = summaries.get("short_summary", "")
            detailed = summaries.get("detailed_summary", "")

            if not short or not detailed:
                raise ValueError("Bundled summary response was incomplete")

            log_phase(
                logger,
                "summary.both",
                "total",
                total_started,
                short_chars=len(short),
                detailed_chars=len(detailed),
            )
            return {
                "short_summary": short,
                "detailed_summary": detailed
            }

        except Exception as e:
            logger.error(f"Error generating summaries: {e}")
            phase_started = time.perf_counter()
            short = await self.generate_short_summary(text, study_context=study_context, topic=topic)
            detailed = await self.generate_detailed_summary(text, study_context=study_context, topic=topic)
            log_phase(
                logger,
                "summary.both",
                "fallback_dual_calls",
                phase_started,
                short_chars=len(short),
                detailed_chars=len(detailed),
            )
            log_phase(logger, "summary.both", "total", total_started, path="fallback")
            return {
                "short_summary": short,
                "detailed_summary": detailed
            }

# Global summary generator instance
summary_generator = SummaryGenerator()
