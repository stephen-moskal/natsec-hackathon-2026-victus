"""HTTP client for a running llama-server instance.

llama-server speaks the OpenAI Chat Completions API on `/v1/chat/completions`,
including multimodal `image_url` content blocks for VLMs (Gemma 4, Qwen3-VL).
We use the data-URL form so we don't have to host the image — the JPEG bytes
are base64-encoded inline.

The client owns its httpx.AsyncClient and is itself an async context manager.
"""

import base64
from typing import Any

import httpx
import structlog


log = structlog.get_logger(__name__)


class LlamaCppClient:
    def __init__(self, base_url: str, timeout_s: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_s
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "LlamaCppClient":
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def health(self) -> bool:
        """GET /health → True if 200, False otherwise. Never raises."""
        assert self._client is not None, "use LlamaCppClient as async context manager"
        try:
            resp = await self._client.get(f"{self._base_url}/health")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def describe_frame(
        self,
        jpeg_bytes: bytes,
        prompt: str,
        max_tokens: int = 80,
        temperature: float = 0.2,
    ) -> str:
        """Send one image + prompt to llama-server; return the assistant text.

        Raises httpx.HTTPError on transport/HTTP failure, ValueError on
        unexpected response shape.

        Reasoning models (gemma4, deepseek-r1, qwen-qwq) emit their output
        in `reasoning_content` until they hit the final-answer marker. For
        a describe-what-you-see prompt the reasoning IS the description we
        want, so we fall back to `reasoning_content` when `content` is
        empty. max_tokens defaults to 512 to give the model headroom to
        finish the CoT — at 256 it runs out mid-thought.
        """
        assert self._client is not None, "use LlamaCppClient as async context manager"

        b64 = base64.b64encode(jpeg_bytes).decode("ascii")
        payload: dict[str, Any] = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                    ],
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        resp = await self._client.post(
            f"{self._base_url}/v1/chat/completions",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()

        body = resp.json()
        try:
            msg = body["choices"][0]["message"]
            content = msg.get("content") or msg.get("reasoning_content") or ""
            return content
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"unexpected llama-server response shape: {body!r}") from exc
