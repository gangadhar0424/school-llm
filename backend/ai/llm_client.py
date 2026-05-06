"""
LLM provider abstraction (Phase 3).

Exposes a single `LLMClient` interface that the evaluator (and any other
caller) talks to. Concrete implementations:

    OllamaWrappedClient    — wraps the existing OllamaClient (development)
    AnthropicLLMClient     — Claude API with prompt caching (production)

Switch via env var `LLM_PROVIDER`:
    LLM_PROVIDER=ollama     → local Ollama (default; dev)
    LLM_PROVIDER=anthropic  → Claude API (prod; requires ANTHROPIC_API_KEY)

The evaluator already calls `ollama_client.chat(messages=..., model=...,
temperature=..., max_tokens=..., response_format=..., extra_options=...)`,
so each concrete client mimics that signature. Drop-in replacement.

Prompt caching:
  Anthropic supports caching the static parts of the prompt (system message,
  rubric block, examples) so repeated calls pay tokens only for the changing
  parts. This module marks the system message with cache_control to enable it.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Protocol

from config import settings

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Minimal interface every concrete client must implement."""

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Any] = None,
        extra_options: Optional[Dict[str, Any]] = None,
    ) -> str:
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Ollama wrapper
# ─────────────────────────────────────────────────────────────────────────────
class OllamaWrappedClient:
    """Thin wrapper that just forwards to the existing OllamaClient.

    Kept as a separate class so that future logic (provider-specific
    instrumentation, retries, etc.) can live here without polluting the
    base Ollama client.
    """

    def __init__(self):
        from ai.ollama_client import ollama_client
        self._inner = ollama_client
        self.provider = "ollama"

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Any] = None,
        extra_options: Optional[Dict[str, Any]] = None,
    ) -> str:
        return await self._inner.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            extra_options=extra_options,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Anthropic / Claude client (with prompt caching)
# ─────────────────────────────────────────────────────────────────────────────
class AnthropicLLMClient:
    """Claude API client. Uses the official `anthropic` SDK if installed,
    else falls back to raw HTTP via `requests` (no extra dependency needed).

    Prompt caching: when enabled, the system message is sent with
    cache_control={"type": "ephemeral"} so subsequent calls within the
    cache window (~5 min) bill only the user message tokens. This is
    important for batch evaluations that share a static rubric.
    """

    def __init__(self):
        self.api_key = settings.ANTHROPIC_API_KEY
        self.default_model = settings.ANTHROPIC_MODEL
        self.default_max_tokens = settings.ANTHROPIC_MAX_TOKENS
        self.use_caching = bool(settings.ANTHROPIC_PROMPT_CACHING)
        self.provider = "anthropic"

        if not self.api_key:
            raise RuntimeError(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file."
            )

        # Try the official SDK; fall back to HTTP if not installed
        try:
            import anthropic  # noqa: F401
            self._sdk_available = True
        except ImportError:
            logger.info("anthropic SDK not installed; using raw HTTP fallback")
            self._sdk_available = False

    # ──────────────────────────────────────────────────────────────────
    # Message construction with prompt caching
    # ──────────────────────────────────────────────────────────────────
    def _split_messages(
        self, messages: List[Dict[str, str]]
    ) -> tuple[List[Dict], List[Dict]]:
        """Split incoming messages into Anthropic's (system, messages) form.

        OpenAI-style uses {"role": "system", ...} as the first message;
        Anthropic uses a separate `system` parameter. We pull all system
        messages out and concatenate them.

        Returns: (system_blocks_with_cache_control, anthropic_messages)
        """
        system_text_parts: List[str] = []
        chat_msgs: List[Dict] = []
        for m in messages or []:
            role = (m.get("role") or "user").lower()
            content = m.get("content") or ""
            if role == "system":
                system_text_parts.append(content)
            else:
                # Anthropic accepts "user" and "assistant"
                anth_role = "user" if role not in ("user", "assistant") else role
                chat_msgs.append({"role": anth_role, "content": content})

        # Build system as a list-of-blocks so we can attach cache_control
        system_blocks: List[Dict] = []
        if system_text_parts:
            joined = "\n\n".join(p for p in system_text_parts if p)
            block: Dict[str, Any] = {"type": "text", "text": joined}
            if self.use_caching:
                # ephemeral = ~5-min cache, the cheapest tier
                block["cache_control"] = {"type": "ephemeral"}
            system_blocks.append(block)

        return system_blocks, chat_msgs

    # ──────────────────────────────────────────────────────────────────
    # Chat call
    # ──────────────────────────────────────────────────────────────────
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Any] = None,
        extra_options: Optional[Dict[str, Any]] = None,
    ) -> str:
        # extra_options is Ollama-specific; ignore for Anthropic
        _ = extra_options
        system_blocks, anth_msgs = self._split_messages(messages)

        # If response_format is "json" the evaluator expects a JSON object —
        # we nudge Claude to return JSON only. Claude doesn't have a strict
        # JSON mode like OpenAI, so we add an instruction to the last user msg.
        if response_format == "json" and anth_msgs:
            last = anth_msgs[-1]
            if not last["content"].rstrip().endswith("}"):
                last["content"] = (
                    last["content"].rstrip()
                    + "\n\nRespond with a single valid JSON object and NOTHING else. "
                      "Do not wrap it in code fences."
                )

        chosen_model = model or self.default_model
        # Map the qwen/llama Ollama default to a real Claude model
        if chosen_model.lower().startswith(("qwen", "llama", "mistral")):
            chosen_model = self.default_model

        payload: Dict[str, Any] = {
            "model": chosen_model,
            "max_tokens": int(max_tokens or self.default_max_tokens),
            "messages": anth_msgs,
        }
        if system_blocks:
            payload["system"] = system_blocks
        if temperature is not None:
            payload["temperature"] = float(temperature)

        if self._sdk_available:
            return await self._call_via_sdk(payload)
        return await self._call_via_http(payload)

    async def _call_via_sdk(self, payload: Dict[str, Any]) -> str:
        import anthropic

        def _do_call() -> str:
            client = anthropic.Anthropic(api_key=self.api_key)
            kwargs = dict(payload)
            # Some SDK versions use beta headers for caching; modern versions
            # accept cache_control inline. Add the header defensively.
            extra_headers = {}
            if self.use_caching:
                extra_headers["anthropic-beta"] = "prompt-caching-2024-07-31"
            resp = client.messages.create(**kwargs, extra_headers=extra_headers or None)
            # Concatenate text blocks
            parts: List[str] = []
            for block in resp.content or []:
                if getattr(block, "type", None) == "text":
                    parts.append(getattr(block, "text", "") or "")
            return "".join(parts).strip()

        try:
            return await asyncio.to_thread(_do_call)
        except Exception as e:
            logger.error(f"Anthropic SDK call failed: {e}")
            raise

    async def _call_via_http(self, payload: Dict[str, Any]) -> str:
        import requests

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        if self.use_caching:
            headers["anthropic-beta"] = "prompt-caching-2024-07-31"

        def _do_call() -> str:
            resp = requests.post(url, json=payload, headers=headers, timeout=120)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Anthropic API error {resp.status_code}: {resp.text[:500]}"
                )
            data = resp.json()
            parts: List[str] = []
            for block in data.get("content", []) or []:
                if block.get("type") == "text":
                    parts.append(block.get("text", "") or "")
            return "".join(parts).strip()

        try:
            return await asyncio.to_thread(_do_call)
        except Exception as e:
            logger.error(f"Anthropic HTTP call failed: {e}")
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Factory + singleton
# ─────────────────────────────────────────────────────────────────────────────
_singleton: Optional[Any] = None


def get_llm_client():
    """Return the active LLM client based on settings.LLM_PROVIDER.
    Cached as a singleton."""
    global _singleton
    if _singleton is not None:
        return _singleton

    provider = (settings.LLM_PROVIDER or "ollama").strip().lower()
    if provider == "anthropic":
        try:
            _singleton = AnthropicLLMClient()
            logger.info(
                f"LLM provider = anthropic (model={settings.ANTHROPIC_MODEL}, "
                f"caching={'on' if settings.ANTHROPIC_PROMPT_CACHING else 'off'})"
            )
        except Exception as e:
            logger.error(f"Failed to init Anthropic client; falling back to Ollama: {e}")
            _singleton = OllamaWrappedClient()
    else:
        _singleton = OllamaWrappedClient()
        logger.info(f"LLM provider = ollama (model={settings.OLLAMA_CHAT_MODEL})")

    return _singleton


def reset_llm_client() -> None:
    """For tests / config changes — drop the cached singleton so next
    call re-reads settings."""
    global _singleton
    _singleton = None
