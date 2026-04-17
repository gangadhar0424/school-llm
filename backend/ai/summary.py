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
from ai.ollama_client import ollama_client
from timing_utils import log_phase

logger = logging.getLogger(__name__)

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
    
    async def generate_short_summary(self, text: str, study_context: str = "") -> str:
        """
        Generate a concise summary (2-3 paragraphs)
        
        Args:
            text: Full text content to summarize
            
        Returns:
            Short summary
        """
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
            )

            phase_started = time.perf_counter()
            summary = await ollama_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Create an accurate short summary in 2-3 paragraphs. "
                            "Preserve chapter/topic names."
                        )
                    },
                    {"role": "user", "content": source_text}
                ],
                model=self.model,
                temperature=0.2,
                max_tokens=220
            )
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
    
    async def generate_detailed_summary(self, text: str, study_context: str = "") -> str:
        """
        Generate a comprehensive detailed summary
        
        Args:
            text: Full text content to summarize
            
        Returns:
            Detailed summary
        """
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
            )

            phase_started = time.perf_counter()
            summary = await ollama_client.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Give an accurate detailed summary with clear bullet points. "
                            "Include exact chapter/topic names when present."
                        )
                    },
                    {"role": "user", "content": source_text}
                ],
                model=self.model,
                temperature=0.2,
                max_tokens=340
            )
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
    
    async def generate_both_summaries(self, text: str, study_context: str = "") -> Dict[str, str]:
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
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Return ONLY valid JSON with exactly two string fields: "
                        "short_summary and detailed_summary. "
                        "The short summary must be 2-3 concise paragraphs. "
                        "The detailed summary must use 6-8 compact bullet points. "
                        "Preserve exact chapter/topic names when present."
                    )
                },
                {"role": "user", "content": source_text}
            ]

            try:
                phase_started = time.perf_counter()
                content = await ollama_client.chat(
                    messages=messages,
                    model=self.model,
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
                content = await ollama_client.chat(
                    messages=messages,
                    model=self.model,
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
            short = await self.generate_short_summary(text, study_context=study_context)
            detailed = await self.generate_detailed_summary(text, study_context=study_context)
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
