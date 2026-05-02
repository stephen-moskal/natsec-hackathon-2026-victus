"""Outbound telemetry queue.

Collects events from every other module, batches them, and hands them to the
FoundryClient. Owns the heartbeat tick that emits a Position+Status pair on
a fixed cadence regardless of activity.
"""

from typing import Any


class TelemetryStreamer:
    def __init__(self, drone_id: str, heartbeat_interval_s: float = 1.0) -> None:
        self.drone_id = drone_id
        self.heartbeat_interval_s = heartbeat_interval_s

    def emit(self, event: str, fields: dict[str, Any]) -> None:
        """Enqueue an event for outbound delivery. To be implemented in Phase 1."""
        raise NotImplementedError

    async def run(self, foundry_client) -> None:
        """Batch and flush loop, plus heartbeat tick."""
        raise NotImplementedError
