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

    # Multi-model accessors — Ollama only has one chat model installed, so
    # all three return the same value. The split exists so the same call-site
    # code works for both Ollama and Anthropic.
    @property
    def generation_model(self) -> Optional[str]:
        return getattr(settings, "OLLAMA_CHAT_MODEL", None)

    @property
    def evaluation_model(self) -> Optional[str]:
        return getattr(settings, "OLLAMA_CHAT_MODEL", None)

    @property
    def naming_model(self) -> Optional[str]:
        return getattr(settings, "OLLAMA_CHAT_MODEL", None)

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

    # Multi-model accessors — different Claude tiers per purpose. Sonnet for
    # user-facing answers (highest quality), Haiku for evaluation/naming
    # (cheap & fast). Falls back to ANTHROPIC_MODEL if a specific one isn't set.
    @property
    def generation_model(self) -> str:
        return getattr(settings, "ANTHROPIC_GENERATION_MODEL", None) or self.default_model

    @property
    def evaluation_model(self) -> str:
        return getattr(settings, "ANTHROPIC_EVALUATION_MODEL", None) or self.default_model

    @property
    def naming_model(self) -> str:
        return getattr(settings, "ANTHROPIC_NAMING_MODEL", None) or self.default_model

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
# OpenRouter (OpenAI-compatible) — used as an independent JUDGE so the
# evaluator can be a stronger / different model from the one used for
# generation. Currently the eval path opt-in routes through this client when
# OPENROUTER_API_KEY is set; generation still follows LLM_PROVIDER.
# ─────────────────────────────────────────────────────────────────────────────
class OpenRouterLLMClient:
    """OpenAI-compatible client for OpenRouter (https://openrouter.ai).

    Lets the project plug in any of OpenRouter's hundreds of models — including
    free-tier reasoning models like Nemotron 30B — without adding the OpenAI
    SDK as a dependency. Uses raw HTTPS via the `requests` library.
    """

    def __init__(self):
        self.api_key = settings.OPENROUTER_API_KEY
        self.base_url = settings.OPENROUTER_BASE_URL.rstrip("/")
        self.eval_model_name = settings.OPENROUTER_EVAL_MODEL
        self.provider = "openrouter"
        if not self.api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set — add it to your .env "
                "to enable OpenRouter as the judge model."
            )

    # Multi-model accessors — OpenRouter is intended for evaluation only,
    # so generation/naming fall back to the configured model. If callers
    # ask for `.generation_model` here we still return the eval model
    # rather than None so chat() doesn't break, but in practice the
    # judge module is the only consumer.
    @property
    def generation_model(self) -> str:
        return self.eval_model_name

    @property
    def evaluation_model(self) -> str:
        return self.eval_model_name

    @property
    def naming_model(self) -> str:
        return self.eval_model_name

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Any] = None,
        extra_options: Optional[Dict[str, Any]] = None,
    ) -> str:
        import requests

        chosen_model = model or self.eval_model_name
        payload: Dict[str, Any] = {
            "model": chosen_model,
            "messages": [
                {"role": (m.get("role") or "user"), "content": m.get("content") or ""}
                for m in (messages or [])
            ],
        }
        if temperature is not None:
            payload["temperature"] = float(temperature)
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        # OpenAI-compatible JSON mode — most OpenRouter providers honour this.
        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # OpenRouter recommends sending these so usage shows up under
            # your app's name in their dashboard. They're optional.
            "HTTP-Referer": "https://school-llm.local",
            "X-Title": "School LLM",
        }

        def _do_call() -> str:
            resp = requests.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
                timeout=120,
            )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"OpenRouter API error {resp.status_code}: {resp.text[:500]}"
                )
            data = resp.json()
            choices = data.get("choices") or []
            if not choices:
                return ""
            msg = choices[0].get("message") or {}
            # Reasoning models may put their chain-of-thought in
            # `reasoning_content` and the final answer in `content`. We
            # only want the final answer (JSON in our case).
            return msg.get("content") or ""

        try:
            return await asyncio.to_thread(_do_call)
        except Exception as e:
            logger.error(f"OpenRouter call failed: {e}")
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Fallback wrapper — primary → fallback on failure
# ─────────────────────────────────────────────────────────────────────────────
import time


class FallbackLLMClient:
    """Wraps a primary LLM client and falls back to a secondary on failure.

    Why: production reliability. If Ollama crashes or your Claude quota runs
    out mid-day, the app keeps responding instead of throwing 500s at users.

    Behavior:
      - Always try `primary.chat()` first.
      - If it raises any Exception, log it and retry on `fallback.chat()`.
      - If the primary just failed within the last `cooldown` seconds, skip
        it entirely and go straight to fallback (avoids per-request waits
        on a known-dead provider).
      - If both fail, re-raise the original primary exception.
    """

    def __init__(self, primary: Any, fallback: Any, cooldown: int = 60):
        self.primary = primary
        self.fallback = fallback
        self.cooldown = max(0, int(cooldown))
        self._primary_dead_until: float = 0.0
        self._fallback_dead_until: float = 0.0
        self.provider = f"{getattr(primary, 'provider', 'unknown')}+fallback={getattr(fallback, 'provider', 'unknown')}"

    # Multi-model accessors delegate to the primary client. The fallback
    # client's models are only used when the primary fails entirely, in
    # which case the chat() method picks its own default for the request.
    @property
    def generation_model(self):
        return getattr(self.primary, "generation_model", None)

    @property
    def evaluation_model(self):
        return getattr(self.primary, "evaluation_model", None)

    @property
    def naming_model(self):
        return getattr(self.primary, "naming_model", None)

    def _is_in_cooldown(self, until_ts: float) -> bool:
        return until_ts > time.time()

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Any] = None,
        extra_options: Optional[Dict[str, Any]] = None,
    ) -> str:
        primary_name = getattr(self.primary, "provider", "primary")
        fallback_name = getattr(self.fallback, "provider", "fallback")

        # Decide which provider to try first based on cooldown state
        skip_primary = self._is_in_cooldown(self._primary_dead_until)
        if skip_primary:
            logger.info(
                f"Primary LLM ({primary_name}) in cooldown — going directly to {fallback_name}"
            )

        primary_exc: Optional[Exception] = None
        if not skip_primary:
            try:
                return await self.primary.chat(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format=response_format,
                    extra_options=extra_options,
                )
            except Exception as e:
                primary_exc = e
                self._primary_dead_until = time.time() + self.cooldown
                logger.warning(
                    f"Primary LLM ({primary_name}) failed: {type(e).__name__}: {e}. "
                    f"Trying fallback ({fallback_name}). Cooldown {self.cooldown}s."
                )

        # Fallback attempt (skip if it's also in cooldown — saves time)
        if self._is_in_cooldown(self._fallback_dead_until):
            logger.error(
                f"Fallback LLM ({fallback_name}) also in cooldown — both providers down"
            )
            if primary_exc:
                raise primary_exc
            raise RuntimeError(f"Both LLM providers in cooldown ({primary_name}, {fallback_name})")

        try:
            result = await self.fallback.chat(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                extra_options=extra_options,
            )
            if primary_exc:
                logger.info(
                    f"Fallback LLM ({fallback_name}) succeeded after primary "
                    f"({primary_name}) failure"
                )
            return result
        except Exception as fb_exc:
            self._fallback_dead_until = time.time() + self.cooldown
            logger.error(
                f"Fallback LLM ({fallback_name}) also failed: "
                f"{type(fb_exc).__name__}: {fb_exc}"
            )
            # Surface the primary error if we have it (it's usually more
            # diagnostic than the fallback's secondary failure)
            if primary_exc:
                raise primary_exc
            raise


def _try_build_anthropic_client() -> Optional[Any]:
    """Build an Anthropic client only if an API key is configured. Never raises."""
    if not getattr(settings, "ANTHROPIC_API_KEY", ""):
        return None
    try:
        return AnthropicLLMClient()
    except Exception as e:
        logger.warning(f"Could not build Anthropic client for fallback: {e}")
        return None


def _try_build_ollama_client() -> Optional[Any]:
    """Build an Ollama client. Never raises (returns None on failure)."""
    try:
        return OllamaWrappedClient()
    except Exception as e:
        logger.warning(f"Could not build Ollama client for fallback: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Factory + singleton
# ─────────────────────────────────────────────────────────────────────────────
_singleton: Optional[Any] = None


def get_llm_client():
    """Return the active LLM client based on settings.LLM_PROVIDER.
    Wraps the primary in a FallbackLLMClient when both providers are available
    (and LLM_FALLBACK_ENABLED is true). Cached as a singleton."""
    global _singleton
    if _singleton is not None:
        return _singleton

    provider = (settings.LLM_PROVIDER or "ollama").strip().lower()
    fallback_enabled = bool(getattr(settings, "LLM_FALLBACK_ENABLED", True))
    cooldown = int(getattr(settings, "LLM_FALLBACK_COOLDOWN", 60))

    # Build the primary client
    primary: Optional[Any] = None
    if provider == "anthropic":
        primary = _try_build_anthropic_client()
        if primary is None:
            logger.error("Failed to init Anthropic client; using Ollama as primary")
            primary = _try_build_ollama_client()
    else:
        primary = _try_build_ollama_client()

    if primary is None:
        # Last resort — try the other provider
        primary = _try_build_anthropic_client()
        if primary is None:
            raise RuntimeError(
                "Could not initialize any LLM provider (Ollama or Anthropic). "
                "Check OLLAMA_BASE_URL or ANTHROPIC_API_KEY."
            )

    # Build the fallback client (the OTHER provider)
    fallback: Optional[Any] = None
    if fallback_enabled:
        primary_kind = getattr(primary, "provider", "").lower()
        if primary_kind == "anthropic":
            fallback = _try_build_ollama_client()
        elif primary_kind == "ollama":
            fallback = _try_build_anthropic_client()

    if fallback is not None:
        _singleton = FallbackLLMClient(primary, fallback, cooldown=cooldown)
        logger.info(
            f"LLM provider = {getattr(primary, 'provider', '?')} "
            f"(fallback={getattr(fallback, 'provider', '?')}, cooldown={cooldown}s)"
        )
    else:
        _singleton = primary
        if fallback_enabled:
            logger.info(
                f"LLM provider = {getattr(primary, 'provider', '?')} "
                f"(no fallback — other provider not configured)"
            )
        else:
            logger.info(
                f"LLM provider = {getattr(primary, 'provider', '?')} "
                f"(fallback disabled via LLM_FALLBACK_ENABLED=false)"
            )

    return _singleton


def reset_llm_client() -> None:
    """For tests / config changes — drop the cached singleton so next
    call re-reads settings."""
    global _singleton
    _singleton = None
