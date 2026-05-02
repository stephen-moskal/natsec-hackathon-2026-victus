"""HTTP client for talking to Foundry.

Two responsibilities:

1. Outbound: POST telemetry envelopes one-at-a-time to the Foundry HTTPS
   Listener. Listener accepts a single JSON object per request (1 MB cap).
   Phase 1.1 adds an offline JSONL buffer and ``drain_buffer`` semantics.

2. Inbound: poll a Foundry TS v2 query function (``pollCommands``) for new
   commands addressed to this drone, validate them through ``protocol``, and
   return them for the main loop to dispatch.

Auth: bearer token from a TokenProvider. mTLS is post-hackathon.
"""

from typing import Any

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .auth import TokenProvider
from .protocol import Envelope, decode_command, encode_telemetry


log = structlog.get_logger(__name__)


class FoundryClient:
    def __init__(
        self,
        token_provider: TokenProvider,
        listener_url: str,
        functions_url: str,
        drone_id: str,
        buffer_path: str,
        timeout_s: float = 10.0,
    ) -> None:
        self._token_provider = token_provider
        self._listener_url = listener_url
        self._functions_url = functions_url.rstrip("/")
        self._drone_id = drone_id
        self._buffer_path = buffer_path
        self._timeout = timeout_s
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "FoundryClient":
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *exc_info) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _auth_headers(self) -> dict[str, str]:
        token = await self._token_provider.token()
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def post_telemetry(self, batch: list[dict[str, Any]]) -> None:
        """POST each envelope to the listener. Buffer to disk on failure (Phase 1.1)."""
        assert self._client is not None, "use FoundryClient as async context manager"
        for envelope in batch:
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=0.5, max=4),
                    retry=retry_if_exception_type(
                        (httpx.TransportError, httpx.HTTPStatusError)
                    ),
                    reraise=True,
                ):
                    with attempt:
                        resp = await self._client.post(
                            self._listener_url,
                            json=envelope,
                            headers=await self._auth_headers(),
                        )
                        if resp.status_code >= 500:
                            resp.raise_for_status()
                        if resp.status_code >= 400:
                            log.error(
                                "telemetry_post_4xx",
                                status=resp.status_code,
                                body=resp.text[:500],
                                message_id=envelope["message_id"],
                            )
                            return
            except Exception as exc:
                log.error(
                    "telemetry_post_failed_buffering_pending",
                    message_id=envelope["message_id"],
                    error=str(exc),
                )
                # TODO Phase 1.1: append envelope to JSONL buffer at self._buffer_path

    async def poll_commands(self, since_message_id: str | None) -> list[Envelope]:
        """Call the pollCommands query function; return validated command envelopes."""
        assert self._client is not None, "use FoundryClient as async context manager"
        url = f"{self._functions_url}/pollCommands/execute"
        body = {
            "parameters": {
                "droneId": self._drone_id,
                "sinceMessageId": since_message_id,
            }
        }
        try:
            resp = await self._client.post(
                url, json=body, headers=await self._auth_headers()
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("poll_commands_failed", error=str(exc))
            return []

        data = resp.json()
        # Foundry function responses wrap output in {"value": ...} for query functions.
        raw_commands = data.get("value", data).get("commands", [])
        envelopes: list[Envelope] = []
        for raw in raw_commands:
            try:
                envelopes.append(decode_command(raw))
            except Exception as exc:
                log.error("invalid_command_dropped", error=str(exc), raw=raw)
        return envelopes

    async def ack_command(
        self, command_id: str, result: str, reason: str | None = None
    ) -> None:
        """Emit a CommandAck telemetry event for the given command."""
        fields: dict[str, Any] = {"command_id": command_id, "result": result}
        if reason is not None:
            fields["reason"] = reason
        envelope = encode_telemetry(
            sender=f"drone-{self._drone_id}",
            event="CommandAck",
            fields=fields,
        )
        await self.post_telemetry([envelope])

    async def drain_buffer(self) -> None:
        """Flush any buffered telemetry from disk in original order. Phase 1.1."""
        return None
