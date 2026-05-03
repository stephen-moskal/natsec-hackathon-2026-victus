"""On-board mission state.

Tracks the most recent ASSIGN_MISSION command so its system_prompt can be
included as context for every subsequent verb. Mission state is in-memory
only — restarting the edge clears it. The operator can re-issue ASSIGN_MISSION
to restore.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class CurrentMission:
    mission_id: str
    name: str
    system_prompt: str


class MissionState:
    """Holds the most recently accepted mission for use as prompt context."""

    def __init__(self) -> None:
        self.current: CurrentMission | None = None

    def update_from_command(self, env: Any) -> None:
        """If the command is ASSIGN_MISSION, capture mission_id/name/system_prompt.

        Accepts an `Envelope`-like object that exposes a `payload` dict with
        `verb` and `params`. Other verbs are ignored.
        """
        payload = getattr(env, "payload", None) or {}
        if payload.get("verb") != "ASSIGN_MISSION":
            return
        params = payload.get("params") or {}
        if not isinstance(params, dict):
            return
        mission_id = str(params.get("mission_id") or "").strip()
        name = str(params.get("name") or "").strip()
        system_prompt = str(params.get("system_prompt") or "").strip()
        if not (mission_id and name and system_prompt):
            return
        self.current = CurrentMission(
            mission_id=mission_id,
            name=name,
            system_prompt=system_prompt,
        )

    def context_block(self) -> str:
        """Multi-line block to splice into a verb-specific prompt header.

        Returns an empty string when no mission is active so the surrounding
        prompt template can render cleanly without conditional branches.
        """
        if self.current is None:
            return ""
        return (
            f"Active mission: \"{self.current.name}\" (id {self.current.mission_id[:8]})\n"
            f"Mission system prompt: {self.current.system_prompt}"
        )
