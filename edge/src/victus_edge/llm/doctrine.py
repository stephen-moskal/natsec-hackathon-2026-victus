"""Doctrine loader + mission-overlay composer.

The on-board model's system prompt is the canonical drone doctrine markdown
(`shared/protocol/prompts/doctrine.system.md`). When the operator issues an
`ASSIGN_MISSION` command, the runtime substitutes the operator's
`system_prompt` between the `<MISSION_OVERLAY>` markers in the doctrine —
exactly as §7 of the doctrine specifies. Every subsequent reasoning step
sees the doctrine + mission overlay together, so the model is mission-aware
without us having to mention the mission elsewhere in the prompt.
"""

from pathlib import Path
from typing import Optional

from .mission_state import MissionState


# Resolve the doctrine path relative to this file. Repo layout:
#   <repo>/edge/src/victus_edge/llm/doctrine.py    (this file)
#   <repo>/shared/protocol/prompts/doctrine.system.md
# parents[4] of this file is <repo>.
_DOCTRINE_PATH = (
    Path(__file__).resolve().parents[4]
    / "shared" / "protocol" / "prompts" / "doctrine.system.md"
)

# The placeholder block in the doctrine that we replace per call.
_OVERLAY_PLACEHOLDER = (
    "<MISSION_OVERLAY>\n"
    "(no mission assigned — the runtime substitutes the operator's "
    "`system_prompt` here when an `ASSIGN_MISSION` command is active)\n"
    "</MISSION_OVERLAY>"
)

# Loaded once at module import. If the file is missing we fall back to a
# minimal stub so the edge still starts (with a clear marker in the prompt
# saying the doctrine wasn't found — rather than crashing).
try:
    _DOCTRINE_TEXT = _DOCTRINE_PATH.read_text(encoding="utf-8")
except OSError:
    _DOCTRINE_TEXT = (
        "# VICTUS — Drone Doctrine (FALLBACK — doctrine.system.md not found)\n\n"
        "You are an on-board UAV reasoner. Reply with CMD/REPLY/RATIONALE lines.\n\n"
        + _OVERLAY_PLACEHOLDER + "\n"
    )


def _format_overlay(ms: MissionState) -> str:
    """Build the overlay block from the active mission state."""
    if ms.current is None:
        return _OVERLAY_PLACEHOLDER
    return (
        "<MISSION_OVERLAY>\n"
        f"Mission name: {ms.current.name}\n"
        f"Mission ID: {ms.current.mission_id}\n\n"
        f"{ms.current.system_prompt}\n"
        "</MISSION_OVERLAY>"
    )


def compose_system_prompt(mission_state: Optional[MissionState] = None) -> str:
    """Return the full doctrine with the active mission injected at §7."""
    if mission_state is None:
        return _DOCTRINE_TEXT
    return _DOCTRINE_TEXT.replace(_OVERLAY_PLACEHOLDER, _format_overlay(mission_state))


def doctrine_text() -> str:
    """Read-only accessor for the raw doctrine (for tests / debug)."""
    return _DOCTRINE_TEXT
