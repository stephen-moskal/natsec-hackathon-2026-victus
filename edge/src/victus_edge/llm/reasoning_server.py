"""Tiny HTTP server that exposes the latest reasoning step over the local LAN.

Mirrors ``vision/frame_server.py`` for the LLM trace path. The BFF proxies
``GET /reasoning`` here so the operator UI can display the LLM's decision +
rationale within seconds of the command being issued — bypassing Foundry's
batch pipeline for live display while the same trace also lands in
``raw_telemetry`` for permanent storage.

Wire it into ``main.py`` alongside ``_command_poller`` and ``_telemetry_emitter``:

    store = ReasoningStore()
    await asyncio.gather(
        _command_poller(client, cfg, reasoner, store),
        _telemetry_emitter(client, cfg),
        run_reasoning_server(store),
    )
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Optional

import structlog


log = structlog.get_logger(__name__)

REASONING_SERVER_PORT = 8889


class ReasoningStore:
    """Asyncio-safe single-slot store for the latest ReasoningOutput as JSON."""

    def __init__(self) -> None:
        self._latest: Optional[dict] = None

    def put(
        self,
        *,
        command_id: str,
        verb: str,
        decision: str,
        rationale: str,
        tokens: int,
    ) -> None:
        self._latest = {
            "command_id": command_id,
            "verb": verb,
            "decision": decision,
            "rationale": rationale,
            "tokens": tokens,
            "observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def get(self) -> Optional[dict]:
        return self._latest


async def run_reasoning_server(store: ReasoningStore) -> None:
    """Start the asyncio HTTP server. Returns when the server stops."""

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readline()                                # request line
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):                  # end of headers
                    break

            latest = store.get()
            if latest is None:
                body = b"{\"error\":\"no reasoning yet\"}"
                status = b"HTTP/1.1 503 No Reasoning Yet\r\n"
            else:
                body = json.dumps(latest).encode("utf-8")
                status = b"HTTP/1.1 200 OK\r\n"

            headers = (
                status
                + b"Content-Type: application/json\r\n"
                + b"Cache-Control: no-store\r\n"
                + b"Access-Control-Allow-Origin: *\r\n"
                + f"Content-Length: {len(body)}\r\n\r\n".encode()
            )
            writer.write(headers + body)
            await writer.drain()
        except Exception:                                          # noqa: BLE001 — keep server alive
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle_client, "0.0.0.0", REASONING_SERVER_PORT)
    log.info("reasoning_http_server_started", port=REASONING_SERVER_PORT)
    async with server:
        await server.serve_forever()
