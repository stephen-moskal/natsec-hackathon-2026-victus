"""On-board reasoning model.

Dispatches every operator command to a verb-appropriate path:

  * **VISION verbs** (REPORT/SEARCH/OBSERVE/TRACK/IDENTIFY) — pull the latest
    webcam frame from the shared FrameStore and call the multimodal LLM with
    a verb-specific prompt. The LLM produces a tactical description of what
    it actually sees relevant to the command.

  * **MOTION verbs** (GOTO/ALTITUDE/LOITER) — text-only call. The LLM emits a
    MAVLink-style structured JSON payload in the rationale that downstream
    autonomy code (or a human reviewer) can act on.

  * **SAFETY verbs** (ABORT/RTB) — short text-only acknowledgment.

  * **ASSIGN_MISSION** — captures the new mission into `MissionState` so
    every subsequent command's prompt includes the mission's system prompt
    as context. The reasoner still produces a confirmation reasoning step
    for visibility in the UI.

The mock backend (used in tests / no-LLM mode) returns deterministic
responses so the rest of the pipeline can be tested without llama-server.
"""

from dataclasses import dataclass
import json
import re
from typing import Any

from .http_client import LlamaCppClient
from .mission_state import MissionState

# Late imports to avoid a hard dependency on the vision module when the
# reasoner is constructed without a frame store (unit tests, mock backend).
try:
    from ..vision.frame_server import FrameStore
except Exception:  # noqa: BLE001
    FrameStore = None  # type: ignore[assignment, misc]


# ── Verb categories ───────────────────────────────────────────────────────

_VISION_VERBS = frozenset({"REPORT", "SEARCH", "OBSERVE", "TRACK", "IDENTIFY"})
_MOTION_VERBS = frozenset({"GOTO", "ALTITUDE", "LOITER"})
_SAFETY_VERBS = frozenset({"ABORT", "RTB"})


# ── Data classes ──────────────────────────────────────────────────────────

@dataclass
class ReasoningInput:
    intent: dict           # current command payload (verb, params, priority, …)
    detections: list[dict] # recent vision detections (unused for now)
    frame_jpeg: bytes | None  # optional override; if None the reasoner pulls from FrameStore


@dataclass
class ReasoningOutput:
    action: dict           # autonomy-controller action (mostly noop today)
    decision: str          # short label
    rationale: str         # full natural-language explanation, <= 500 chars on the wire
    tokens: int


# ── Prompt templates ──────────────────────────────────────────────────────

_BASE_HEADER = (
    "You are the on-board tactical reasoner for an autonomous UAV.\n"
    "{mission_block}"
    "Operator natural-language intent: {nl_context}\n"
    "Current command: {verb} with structured params: {structured_params}\n"
)

_VISION_TAIL = (
    "The image attached is the live view from the drone's camera right now. "
    "Describe what you see in the frame relevant to this command.\n\n"
    "Respond in EXACTLY this format, nothing else:\n"
    "DECISION: <one short imperative line, ~10 words>\n"
    "RATIONALE: <2-3 sentences describing the visual scene and how it relates to the command>"
)

_MOTION_TAIL = (
    "Produce the MAVLink-style command that satisfies this verb. "
    "Use realistic lat/lon if a destination/landmark is named (approximate from your knowledge). "
    "Output a single JSON object with keys appropriate for the verb (e.g. mavlink_cmd, lat, lon, alt_m, "
    "altitude_change_ft, direction, duration_s, bearing_deg).\n\n"
    "Respond in EXACTLY this format, nothing else:\n"
    "DECISION: <one short imperative line>\n"
    "RATIONALE: ```json\n<the json object>\n```\nThen ONE sentence justifying the choice."
)

_SAFETY_TAIL = (
    "Confirm the safe action you will take. The operator wants you to halt or return.\n\n"
    "Respond in EXACTLY this format:\n"
    "DECISION: <one short imperative>\n"
    "RATIONALE: <one sentence describing the action and its safety implication>"
)

_MISSION_ACCEPT_TAIL = (
    "You are accepting a new mission. In one short paragraph confirm you understand "
    "the mission and how you will approach it.\n\n"
    "Respond in EXACTLY this format:\n"
    "DECISION: <one short line summarizing the mission>\n"
    "RATIONALE: <2-3 sentences on how you'll execute the mission's intent>"
)

_NO_FRAME_NOTE = (
    "\n[No live camera frame is available right now — reason about the command "
    "without visual evidence; note in your rationale that no view was available.]"
)


# ── Helpers ───────────────────────────────────────────────────────────────

def _build_header(verb: str, intent: dict, mission_state: MissionState | None) -> str:
    params = intent.get("params") or {}
    nl_context = ""
    structured = {}
    if isinstance(params, dict):
        nl_context = str(params.get("nl_context") or "(none)")
        structured = {k: v for k, v in params.items() if k != "nl_context"}

    mission_block = ""
    if mission_state is not None and mission_state.current is not None:
        mission_block = mission_state.context_block() + "\n"

    return _BASE_HEADER.format(
        mission_block=mission_block,
        nl_context=nl_context,
        verb=verb,
        structured_params=json.dumps(structured, separators=(",", ":")),
    )


_DECISION_RE = re.compile(r"DECISION:\s*(.+?)(?:\n|$)", re.IGNORECASE)
_RATIONALE_RE = re.compile(r"RATIONALE:\s*(.+)", re.IGNORECASE | re.DOTALL)


def _parse_decision_rationale(text: str) -> tuple[str, str]:
    """Extract DECISION + RATIONALE lines. Falls back to first/rest split."""
    text = text.strip()
    decision_m = _DECISION_RE.search(text)
    rationale_m = _RATIONALE_RE.search(text)
    if decision_m and rationale_m:
        return decision_m.group(1).strip()[:120], rationale_m.group(1).strip()[:500]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "(no decision)", "(empty model response)"
    return lines[0][:120], (" ".join(lines[1:]) or text)[:500]


# ── Reasoner ──────────────────────────────────────────────────────────────

class Reasoner:
    """Backend-agnostic, verb-aware reasoner.

    `client` is required for the `llama_cpp_server` backend and ignored by
    `mock`. `frame_store` and `mission_state` are optional — when absent the
    vision path falls back to text-only and mission context is empty.
    """

    def __init__(
        self,
        backend: str,
        client: LlamaCppClient | None = None,
        model_path: str | None = None,
        frame_store: Any = None,
        mission_state: MissionState | None = None,
    ) -> None:
        self.backend = backend
        self.client = client
        self.model_path = model_path
        self.frame_store = frame_store
        self.mission_state = mission_state
        if backend == "llama_cpp_server" and client is None:
            raise ValueError("llama_cpp_server backend requires a LlamaCppClient")

    async def step(self, inputs: ReasoningInput) -> ReasoningOutput:
        verb = (inputs.intent or {}).get("verb", "")
        if self.backend == "mock":
            return self._mock_step(verb)
        if self.backend == "llama_cpp_server":
            return await self._llama_step(verb, inputs)
        raise NotImplementedError(f"unknown reasoner backend: {self.backend}")

    # ── Mock path ──────────────────────────────────────────────────────────

    def _mock_step(self, verb: str) -> ReasoningOutput:
        return ReasoningOutput(
            action={"do": "noop"},
            decision=f"mock-{verb.lower() or 'noop'}",
            rationale=f"mock backend received verb={verb}",
            tokens=0,
        )

    # ── Real LLM path ─────────────────────────────────────────────────────

    async def _llama_step(self, verb: str, inputs: ReasoningInput) -> ReasoningOutput:
        assert self.client is not None
        header = _build_header(verb, inputs.intent or {}, self.mission_state)

        if verb == "ASSIGN_MISSION":
            # Mission state was updated by the caller before step(). Build the
            # confirmation prompt from the now-current mission.
            return await self._chat_with(verb, header + _MISSION_ACCEPT_TAIL)

        if verb in _VISION_VERBS:
            jpeg = inputs.frame_jpeg
            if jpeg is None and self.frame_store is not None:
                jpeg = self.frame_store.get()
            if jpeg is None:
                # No frame available — fall back to text-only path with a note.
                return await self._chat_with(verb, header + _VISION_TAIL + _NO_FRAME_NOTE)
            return await self._describe_with(verb, header + _VISION_TAIL, jpeg)

        if verb in _MOTION_VERBS:
            return await self._chat_with(verb, header + _MOTION_TAIL)

        if verb in _SAFETY_VERBS:
            return await self._chat_with(verb, header + _SAFETY_TAIL)

        # Unknown verb — give the LLM a generic prompt so we still get a trace.
        return await self._chat_with(verb, header + _SAFETY_TAIL)

    async def _chat_with(self, verb: str, user_prompt: str) -> ReasoningOutput:
        assert self.client is not None
        text = await self.client.chat_completion(
            [
                {"role": "system", "content": "You are an on-board tactical UAV reasoner. Follow the user's required output format exactly."},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=300,
            temperature=0.2,
        )
        decision, rationale = _parse_decision_rationale(text)
        return ReasoningOutput(
            action={"do": "noop", "verb": verb},
            decision=decision,
            rationale=rationale,
            tokens=len(text.split()),
        )

    async def _describe_with(self, verb: str, prompt: str, jpeg: bytes) -> ReasoningOutput:
        assert self.client is not None
        text = await self.client.describe_frame(jpeg, prompt=prompt, max_tokens=300, temperature=0.2)
        decision, rationale = _parse_decision_rationale(text)
        return ReasoningOutput(
            action={"do": "noop", "verb": verb},
            decision=decision,
            rationale=rationale,
            tokens=len(text.split()),
        )
