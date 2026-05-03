"""On-board reasoning model — doctrine-driven, mission-aware.

The model's system prompt is `shared/protocol/prompts/doctrine.system.md`
with the active mission's `system_prompt` injected between the
`<MISSION_OVERLAY>` markers (§7 of the doctrine). The user message is the
operator's command rendered in plain English. The model reply follows the
doctrine §8 output contract:

    CMD: <KEYWORD> key=value ...
    REPLY: <RESPONSE_KEYWORD> [reason="..."]
    RATIONALE: <one sentence>

Per doctrine §2 ("You see one camera frame per reasoning step") we attach
the latest webcam frame to every multimodal-capable call. When no frame is
available we fall back to text-only with a note.
"""

from dataclasses import dataclass
import json
import re
from typing import Any

from .doctrine import compose_system_prompt
from .http_client import LlamaCppClient
from .mission_state import MissionState

# Late/optional import so unit tests can construct a Reasoner without OpenCV.
try:
    from ..vision.frame_server import FrameStore
except Exception:  # noqa: BLE001
    FrameStore = None  # type: ignore[assignment, misc]


# ── Data classes ──────────────────────────────────────────────────────────

@dataclass
class ReasoningInput:
    intent: dict           # current command payload (verb, params, priority, …)
    detections: list[dict] # recent vision detections (unused for now)
    frame_jpeg: bytes | None  # optional override; if None we try the FrameStore


@dataclass
class ReasoningOutput:
    action: dict           # parsed CMD lines as a list under action["cmds"]
    decision: str          # short label combining REPLY + first CMD
    rationale: str         # the doctrine RATIONALE line, ≤ 500 chars on the wire
    tokens: int


# ── User-prompt phrasing ──────────────────────────────────────────────────
# We render the wire-protocol command as plain-English tasking the doctrine
# model is trained to receive. The mapping below converts between the
# wire-protocol verb names (drone_command_policy.json) and the doctrine
# vocabulary (§3) where they differ — most overlap one-to-one, ALTITUDE
# splits into CLIMB/DESCEND, GOTO uses `location` instead of `destination`.

def _natural_language_task(intent: dict) -> str:
    verb = (intent or {}).get("verb", "")
    params = (intent or {}).get("params") or {}
    if not isinstance(params, dict):
        params = {}
    nl = str(params.get("nl_context") or "").strip()
    structured = {k: v for k, v in params.items() if k != "nl_context"}

    # Natural-language verb phrasing
    phrase: str
    if verb == "ABORT":
        phrase = "Abort the current task and enter a safe holding state."
    elif verb == "RTB":
        phrase = "Return to base."
    elif verb == "GOTO":
        dest = structured.get("destination") or structured.get("location") or "(unspecified)"
        alt = structured.get("altitude")
        phrase = f"Go to {dest}." + (f" Climb to {alt} ft AGL on arrival." if alt else "")
    elif verb == "ALTITUDE":
        direction = (structured.get("direction") or "").upper()
        alt = structured.get("altitude")
        if direction == "CLIMB":
            phrase = f"Climb to {alt} ft AGL." if alt else "Climb."
        elif direction == "DESCEND":
            phrase = f"Descend to {alt} ft AGL." if alt else "Descend."
        else:
            phrase = f"Change altitude to {alt} ft AGL." if alt else "Change altitude."
    elif verb == "LOITER":
        loc = structured.get("location") or "current position"
        dur = structured.get("duration") or "PT10M"
        phrase = f"Loiter at {loc} for {dur}."
    elif verb == "SEARCH":
        area = structured.get("area") or "(unspecified area)"
        target = structured.get("target") or "(unspecified target)"
        pattern = structured.get("pattern") or "parallel sweep"
        phrase = f"Search {area} for {target} using a {pattern}."
    elif verb == "OBSERVE":
        target = structured.get("target") or "(unspecified target)"
        mode = structured.get("mode") or "static"
        dur = structured.get("duration") or "PT30M"
        interval = structured.get("reportInterval") or "PT60S"
        phrase = f"Observe {target} in {mode} mode for {dur}, reporting every {interval}."
    elif verb == "REPORT":
        subject = structured.get("subject") or "the current scene"
        interval = structured.get("interval")
        phrase = (
            f"Report a SITREP on {subject}."
            + (f" Repeat every {interval}." if interval else "")
        )
    elif verb == "TRACK":
        target = structured.get("target") or "(unspecified target)"
        standoff = structured.get("standOffMeters")
        phrase = f"Track {target}." + (f" Maintain {standoff} m stand-off." if standoff else "")
    elif verb == "IDENTIFY":
        target = structured.get("target") or "(unspecified target)"
        phrase = f"Identify the {target}."
    elif verb == "ASSIGN_MISSION":
        # The mission overlay was already updated before this call; the
        # doctrine system prompt now carries the new mission. We just need
        # the model to acknowledge.
        name = structured.get("name") or "(unnamed)"
        phrase = (
            f"Operator has installed mission overlay \"{name}\". "
            "The mission's system_prompt is now in effect. Acknowledge with WILCO "
            "and a one-sentence rationale describing your understanding of the mission."
        )
    else:
        phrase = f"Operator command: {verb} with parameters {json.dumps(structured, separators=(',', ':'))}."

    if nl:
        phrase += f" Operator clarification: \"{nl}\""
    return phrase


# ── Output parser (doctrine §8) ───────────────────────────────────────────

_CMD_RE = re.compile(r"^\s*CMD:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
_REPLY_RE = re.compile(r"^\s*REPLY:\s*(.+?)\s*$", re.MULTILINE | re.IGNORECASE)
# RATIONALE captures from `RATIONALE:` up to (but not including) the next
# MAVLINK: line, or end-of-text. Non-greedy + lookahead ensures we don't
# pull MAVLINK content into the rationale prose.
_RATIONALE_RE = re.compile(
    r"^\s*RATIONALE:\s*(.+?)(?=\n\s*MAVLINK:|\Z)",
    re.MULTILINE | re.IGNORECASE | re.DOTALL,
)
_MAVLINK_RE = re.compile(
    r"^\s*MAVLINK:\s*(.+?)\s*$",
    re.MULTILINE | re.IGNORECASE | re.DOTALL,
)


def _parse_doctrine_reply(text: str) -> tuple[list[str], str, str, str | None]:
    """Return (cmd_lines, reply_line, display_rationale, mavlink_json).

    `display_rationale` is the prose RATIONALE with the MAVLINK block appended
    (formatted nicely) so the UI panel shows both pieces in one block.
    `mavlink_json` is the raw MAVLink JSON string (or None).
    """
    text = (text or "").strip()
    cmds = [m.group(1).strip() for m in _CMD_RE.finditer(text)]
    reply_m = _REPLY_RE.search(text)
    rationale_m = _RATIONALE_RE.search(text)
    mavlink_m = _MAVLINK_RE.search(text)

    reply = reply_m.group(1).strip() if reply_m else ""
    rationale = (rationale_m.group(1).strip() if rationale_m else text).strip()
    mavlink = mavlink_m.group(1).strip() if mavlink_m else None

    # Fallback: no structured fields found at all → use first/rest split.
    if not reply and not rationale_m:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines:
            reply = lines[0]
            rationale = " ".join(lines[1:]) or text

    # Compose the display rationale (prose + nicely formatted MAVLink).
    display = rationale
    if mavlink:
        display = f"{rationale}\n\n📡 MAVLINK\n{mavlink}"
    return cmds, reply, display[:800], mavlink


def _decision_label(cmds: list[str], reply: str) -> str:
    """Compose a short decision label for the dashboard."""
    if cmds and reply:
        return f"{reply} · {cmds[0]}"[:160]
    return (cmds[0] if cmds else reply or "(no decision)")[:160]


# ── Reasoner ──────────────────────────────────────────────────────────────

class Reasoner:
    """Doctrine-driven, mission-aware reasoner.

    The doctrine is the system prompt. Mission overlay is injected per call
    via the shared MissionState. The user message is the operator's command
    rendered as plain English. We attach the latest webcam frame when one is
    available so vision-grounded reasoning works for any verb (per doctrine §2).
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
            action={"cmds": [], "verb": verb},
            decision=f"WILCO · mock-{verb.lower() or 'noop'}",
            rationale=f"mock backend received verb={verb}",
            tokens=0,
        )

    # ── Real LLM path ─────────────────────────────────────────────────────

    async def _llama_step(self, verb: str, inputs: ReasoningInput) -> ReasoningOutput:
        assert self.client is not None
        system_prompt = compose_system_prompt(self.mission_state)
        user_text = _natural_language_task(inputs.intent or {})

        # Try to attach a frame — doctrine §2 says every step sees one frame.
        jpeg = inputs.frame_jpeg
        if jpeg is None and self.frame_store is not None:
            jpeg = self.frame_store.get()

        if jpeg is not None:
            text = await self._describe_with(system_prompt, user_text, jpeg)
        else:
            text = await self._chat_with(system_prompt, user_text)

        cmds, reply, rationale, mavlink = _parse_doctrine_reply(text)
        return ReasoningOutput(
            action={"cmds": cmds, "verb": verb, "reply": reply, "mavlink": mavlink},
            decision=_decision_label(cmds, reply),
            rationale=rationale,
            tokens=len(text.split()),
        )

    async def _chat_with(self, system_prompt: str, user_text: str) -> str:
        assert self.client is not None
        return await self.client.chat_completion(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            max_tokens=400,
            temperature=0.2,
        )

    async def _describe_with(self, system_prompt: str, user_text: str, jpeg: bytes) -> str:
        """Multimodal call — system prompt + text task + camera frame."""
        import base64
        assert self.client is not None
        b64 = base64.b64encode(jpeg).decode("ascii")
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            },
        ]
        return await self.client.chat_completion(
            messages, max_tokens=400, temperature=0.2,
        )
