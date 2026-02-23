"""
Ollama client for local LLM calls.
Uses streaming to avoid read timeouts on slow CPU machines.
"""
import asyncio
import logging
import json
from typing import List, Dict, Optional, Any
import requests
from config import settings

logger = logging.getLogger(__name__)

class OllamaClient:
    """Lightweight Ollama HTTP client with streaming support."""

    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.default_model = settings.OLLAMA_CHAT_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT

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
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        options: Dict[str, Any] = {
            "num_ctx": 2048,      # smaller context window = much faster on CPU
        }
        if temperature is not None:
            options["temperature"] = temperature
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        payload: Dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "options": options,
        }

        content = await asyncio.to_thread(self._stream_chat, payload)
        return content

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

ollama_client = OllamaClient()
