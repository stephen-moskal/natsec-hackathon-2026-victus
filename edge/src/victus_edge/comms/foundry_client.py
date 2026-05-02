"""HTTP client for talking to Foundry.

Two responsibilities:

1. Outbound: drain the local telemetry queue and POST batches to the Foundry
   REST API data source webhook. On failure, persist to the offline buffer
   (JSONL on disk). On reconnect, flush the buffer in order.

2. Inbound: long-poll the `pollCommands` Foundry function for new commands
   addressed to this drone, validate them through `protocol`, and enqueue
   them for the main loop.

Auth: bearer token from config. mTLS is post-hackathon.
"""

from typing import Any


class FoundryClient:
    def __init__(self, base_url: str, token: str, drone_id: str, buffer_path: str) -> None:
        self.base_url = base_url
        self.token = token
        self.drone_id = drone_id
        self.buffer_path = buffer_path

    async def post_telemetry(self, batch: list[dict[str, Any]]) -> None:
        """Send a batch; buffer to disk on failure. To be implemented in Phase 1."""
        raise NotImplementedError

    async def poll_commands(self, since_message_id: str | None) -> list[dict[str, Any]]:
        """Long-poll for new commands addressed to this drone."""
        raise NotImplementedError

    async def drain_buffer(self) -> None:
        """Flush any buffered telemetry from disk in original order."""
        raise NotImplementedError
