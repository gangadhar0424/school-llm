"""
Ollama client for local LLM calls.
Uses streaming to avoid read timeouts on slow CPU machines.

Built-in fallback: if Ollama fails (timeout / network / model error), the
client transparently retries the request against Anthropic Claude
(when ANTHROPIC_API_KEY is set and LLM_FALLBACK_ENABLED is true). A short
cooldown prevents hammering a known-dead Ollama instance on every call.
"""
import asyncio
import logging
import time
import json
from typing import List, Dict, Optional, Any
import requests
from config import settings

logger = logging.getLogger(__name__)


# Module-level cooldown trackers. When a backend fails, we skip it for
# `LLM_FALLBACK_COOLDOWN` seconds — prevents UI lag from waiting on a
# known-dead provider on every request.
_ollama_dead_until: float = 0.0
_anthropic_dead_until: float = 0.0


def _is_real_anthropic_key(key: str) -> bool:
    """True only when ANTHROPIC_API_KEY looks like a real key (not empty,
    not the env template placeholder). Saves a 1-2s HTTP roundtrip when
    the user hasn't configured Anthropic yet."""
    if not key:
        return False
    k = key.strip()
    if len(k) < 20:
        return False
    placeholder_markers = (
        "YOUR-KEY-HERE", "YOUR_KEY_HERE", "your-key-here",
        "REPLACE_ME", "REPLACE-ME", "<your", "xxxxx",
    )
    return not any(m in k for m in placeholder_markers)


# ──────────────────────────────────────────────────────────────────────────────
# Up-front availability check — call this BEFORE running expensive pipelines
# (RAG retrieval, chunking, etc.) to short-circuit when no LLM can answer.
# Results are cached for 30s so a quick burst of requests doesn't ping Ollama
# 100 times.
# ──────────────────────────────────────────────────────────────────────────────
_AVAILABILITY_CACHE_TTL = 30
_availability_cache: Dict[str, Any] = {
    "ts": 0.0,
    "ollama": False,
    "anthropic": False,
}


def check_llm_availability(force_refresh: bool = False) -> Dict[str, bool]:
    """Return a snapshot of which LLM providers are currently usable.

    Returns:
        {
            "ollama":    True if Ollama responds to /api/tags within 2s,
            "anthropic": True if API key looks real AND not in cooldown,
            "any":       True if at least one provider is usable,
        }

    Cached for 30s so repeated calls (e.g., from quiz attempt loop) are free.
    Pass `force_refresh=True` to bypass cache (e.g., when retrying after a
    fresh provider config change).
    """
    now = time.time()
    if (
        not force_refresh
        and (now - _availability_cache.get("ts", 0)) < _AVAILABILITY_CACHE_TTL
    ):
        return {
            "ollama": _availability_cache["ollama"],
            "anthropic": _availability_cache["anthropic"],
            "any": _availability_cache["ollama"] or _availability_cache["anthropic"],
        }

    # ── Ollama check (fast HTTP ping, 2s timeout) ─────────────────────────
    ollama_ok = False
    if _ollama_dead_until <= now:
        try:
            base = settings.OLLAMA_BASE_URL.rstrip("/")
            r = requests.get(f"{base}/api/tags", timeout=2)
            ollama_ok = (r.status_code == 200)
        except Exception:
            ollama_ok = False

    # ── Anthropic check (just verify key looks valid + not in cooldown) ──
    anthropic_ok = (
        _is_real_anthropic_key(getattr(settings, "ANTHROPIC_API_KEY", ""))
        and _anthropic_dead_until <= now
    )

    _availability_cache["ts"] = now
    _availability_cache["ollama"] = ollama_ok
    _availability_cache["anthropic"] = anthropic_ok

    return {
        "ollama": ollama_ok,
        "anthropic": anthropic_ok,
        "any": ollama_ok or anthropic_ok,
    }


def invalidate_availability_cache() -> None:
    """Force the next check_llm_availability() call to re-probe both providers."""
    _availability_cache["ts"] = 0.0


class OllamaClient:
    """Lightweight Ollama HTTP client with streaming support + Anthropic fallback."""

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.default_model = settings.OLLAMA_CHAT_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT
        self.keep_alive = "15m"

    # ---------- health / warm-up ----------
    def is_available(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    async def warm_up(self):
        """Pre-load the model so the first real request is fast."""
        try:
            logger.info(f"Warming up model {self.default_model}...")
            await self.chat(
                [{"role": "user", "content": "hi"}],
                max_tokens=5,
            )
            logger.info("Model warm-up complete")
        except Exception as e:
            logger.warning(f"Model warm-up failed (non-fatal): {e}")

    # ---------- low-level POST (streaming) ----------
    def _stream_chat(self, payload: Dict) -> str:
        """
        Stream the response token-by-token.
        This avoids the read-timeout that occurs with stream=False
        on slow CPU machines, because each chunk arrives quickly
        even though the total generation takes a while.
        """
        url = f"{self.base_url}/api/chat"
        payload["stream"] = True
        content_parts: list[str] = []
        try:
            with requests.post(
                url, json=payload, stream=True, timeout=(10, self.timeout)
            ) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        content_parts.append(token)
                    if chunk.get("done"):
                        break
        except requests.exceptions.ConnectionError:
            raise Exception("Cannot connect to Ollama. Make sure Ollama is running.")
        except requests.exceptions.Timeout:
            if content_parts:
                # Return whatever was generated so far
                logger.warning("Ollama timed out but partial response available")
                return "".join(content_parts).strip()
            raise Exception("Ollama timed out. The model may be overloaded — try again.")
        return "".join(content_parts).strip()

    def _post(self, path: str, payload: Dict) -> Dict:
        """Non-streaming POST for embeddings etc."""
        url = f"{self.base_url}{path}"
        response = requests.post(url, json=payload, timeout=(10, self.timeout))
        response.raise_for_status()
        return response.json()

    # ---------- chat ----------
    def _estimate_message_tokens(self, messages: List[Dict[str, str]]) -> int:
        total_chars = sum(len((message or {}).get("content", "")) for message in messages or [])
        return max(1, total_chars // 4)

    def _recommended_num_ctx(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int]
    ) -> int:
        estimated_input_tokens = self._estimate_message_tokens(messages)
        target = estimated_input_tokens + (max_tokens or 256) + 256
        target = max(2048, target)

        # Round up to keep a small safety margin without always using the full global context.
        rounded = ((target + 255) // 256) * 256
        return min(settings.OLLAMA_NUM_CTX, rounded)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Any] = None,
        extra_options: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Chat with Ollama. On failure (and if fallback enabled + Anthropic
        configured), transparently retry the request against Claude so the
        caller never has to think about it."""
        global _ollama_dead_until, _anthropic_dead_until

        fallback_enabled = bool(getattr(settings, "LLM_FALLBACK_ENABLED", True))
        cooldown = int(getattr(settings, "LLM_FALLBACK_COOLDOWN", 60))
        # Treat placeholder keys as "not configured" so we don't waste 1-2s
        # per request on a doomed Anthropic HTTP roundtrip.
        anthropic_available = (
            _is_real_anthropic_key(getattr(settings, "ANTHROPIC_API_KEY", ""))
            and _anthropic_dead_until <= time.time()
        )

        # If we recently failed and a fallback is available, skip Ollama
        skip_ollama = (
            fallback_enabled
            and anthropic_available
            and _ollama_dead_until > time.time()
        )

        ollama_exc: Optional[Exception] = None
        if not skip_ollama:
            options: Dict[str, Any] = {
                "num_ctx": self._recommended_num_ctx(messages, max_tokens),
            }
            if temperature is not None:
                options["temperature"] = temperature
            if max_tokens is not None:
                options["num_predict"] = max_tokens
            if extra_options:
                options.update(extra_options)

            payload: Dict[str, Any] = {
                "model": model or self.default_model,
                "messages": messages,
                "options": options,
                "keep_alive": self.keep_alive,
            }
            if response_format is not None:
                payload["format"] = response_format

            try:
                content = await asyncio.to_thread(self._stream_chat, payload)
                # Success — reset cooldown so future calls hit Ollama again
                if _ollama_dead_until:
                    _ollama_dead_until = 0.0
                return content
            except Exception as e:
                ollama_exc = e
                if fallback_enabled and anthropic_available:
                    _ollama_dead_until = time.time() + cooldown
                    logger.warning(
                        f"Ollama failed: {type(e).__name__}: {e}. "
                        f"Falling back to Anthropic Claude. Cooldown {cooldown}s."
                    )
                else:
                    # No fallback configured (or Anthropic also dead) —
                    # re-raise the original error so caller can decide what
                    # to do (Tier 3 extractive fallback handles this).
                    raise
        else:
            logger.info("Ollama in cooldown; routing directly to Anthropic fallback")

        # ── ANTHROPIC FALLBACK ────────────────────────────────────────────
        try:
            content = await _fallback_to_anthropic(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )
            # Success — clear cooldown
            if _anthropic_dead_until:
                _anthropic_dead_until = 0.0
            return content
        except Exception as fb_exc:
            _anthropic_dead_until = time.time() + cooldown
            logger.error(
                f"Anthropic fallback also failed: {type(fb_exc).__name__}: {fb_exc}. "
                f"Cooldown {cooldown}s."
            )
            # Prefer the original Ollama error if we have it (more diagnostic)
            if ollama_exc is not None:
                raise ollama_exc
            raise

    # ---------- embeddings ----------
    async def embeddings(
        self,
        texts: List[str],
        model: Optional[str] = None
    ) -> List[List[float]]:
        results: List[List[float]] = []
        for text in texts:
            payload = {
                "model": model or settings.OLLAMA_EMBEDDING_MODEL,
                "prompt": text
            }
            data = await asyncio.to_thread(self._post, "/api/embeddings", payload)
            embedding = data.get("embedding") or []
            results.append(embedding)
        return results

# ─────────────────────────────────────────────────────────────────────────────
# Anthropic fallback helper — lazy-imported to avoid hard dependency
# ─────────────────────────────────────────────────────────────────────────────
_cached_anthropic_client: Optional[Any] = None


async def _fallback_to_anthropic(
    messages: List[Dict[str, str]],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    response_format: Optional[Any] = None,
) -> str:
    """Send the same request to Anthropic Claude. Lazy-import to avoid
    circular imports with llm_client.py."""
    global _cached_anthropic_client
    if _cached_anthropic_client is None:
        # Defer the import so loading ollama_client doesn't pull in Anthropic
        from ai.llm_client import AnthropicLLMClient
        _cached_anthropic_client = AnthropicLLMClient()

    return await _cached_anthropic_client.chat(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
    )


ollama_client = OllamaClient()
