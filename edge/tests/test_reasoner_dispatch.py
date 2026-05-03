"""Tests for the doctrine-driven, mission-aware Reasoner.

The reasoner uses doctrine.system.md as the system prompt with the active
mission overlay injected (§7), and parses the model's CMD/REPLY/RATIONALE
output (§8). We mock LlamaCppClient at the method level so we can inspect
the system + user messages and assert which path was taken.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from victus_edge.llm.mission_state import MissionState
from victus_edge.llm.reasoner import Reasoner, ReasoningInput


class _StubFrameStore:
    def __init__(self, jpeg: bytes | None = None) -> None:
        self._jpeg = jpeg

    def get(self) -> bytes | None:
        return self._jpeg


class _RecordingClient:
    """LlamaCppClient stand-in that records calls to chat_completion."""

    def __init__(self, reply: str | None = None) -> None:
        self.reply = reply or (
            "CMD: REPORT subject=\"current scene\"\n"
            "REPLY: ROGER\n"
            "RATIONALE: Acknowledging the report request and providing the current scene description."
        )
        self.chat_calls: list[list[dict]] = []

    async def chat_completion(self, messages: list[dict], **_: Any) -> str:
        self.chat_calls.append(messages)
        return self.reply

    async def describe_frame(self, jpeg: bytes, prompt: str, **_: Any) -> str:  # not used now
        return self.reply


def _intent(verb: str, **params: Any) -> dict:
    return {"verb": verb, "params": params, "priority": "ROUTINE"}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Mock backend stays deterministic ──────────────────────────────────────

def test_mock_backend_returns_mock_decision() -> None:
    r = Reasoner(backend="mock")
    out = _run(r.step(ReasoningInput(intent=_intent("REPORT"), detections=[], frame_jpeg=None)))
    assert "mock-report" in out.decision
    assert "mock backend" in out.rationale


# ── Doctrine drives the system prompt ────────────────────────────────────

def test_system_prompt_is_doctrine() -> None:
    """First message in every chat call is the doctrine system prompt."""
    client = _RecordingClient()
    r = Reasoner(backend="llama_cpp_server", client=client)
    _run(r.step(ReasoningInput(intent=_intent("REPORT"), detections=[], frame_jpeg=None)))
    sys_msg = client.chat_calls[0][0]
    assert sys_msg["role"] == "system"
    # Doctrine has these section anchors — fail loudly if the loader broke.
    assert "VICTUS" in sys_msg["content"]
    assert "Brevity-reply vocabulary" in sys_msg["content"]
    assert "Output contract" in sys_msg["content"]


def test_mission_overlay_injected_into_system_prompt() -> None:
    """ASSIGN_MISSION → mission appears in the doctrine overlay block."""
    client = _RecordingClient()
    ms = MissionState()

    @dataclass
    class _Env:
        payload: dict

    ms.update_from_command(_Env(payload={
        "verb": "ASSIGN_MISSION",
        "params": {
            "mission_id": "mid-12345678",
            "name": "Recon Sector 7",
            "system_prompt": "Scan the harbor and report contacts every 60 seconds.",
        },
    }))
    r = Reasoner(backend="llama_cpp_server", client=client, mission_state=ms)
    _run(r.step(ReasoningInput(intent=_intent("REPORT"), detections=[], frame_jpeg=None)))

    sys_msg = client.chat_calls[0][0]["content"]
    # Mission block should be inside <MISSION_OVERLAY> markers.
    assert "<MISSION_OVERLAY>" in sys_msg
    assert "Recon Sector 7" in sys_msg
    assert "Scan the harbor" in sys_msg
    # Placeholder line should be gone when mission is active.
    assert "(no mission assigned" not in sys_msg


def test_no_mission_keeps_overlay_placeholder() -> None:
    client = _RecordingClient()
    r = Reasoner(backend="llama_cpp_server", client=client, mission_state=MissionState())
    _run(r.step(ReasoningInput(intent=_intent("REPORT"), detections=[], frame_jpeg=None)))
    sys_msg = client.chat_calls[0][0]["content"]
    assert "(no mission assigned" in sys_msg


# ── User prompt is plain-English tasking ─────────────────────────────────

def test_goto_user_prompt_is_natural_language() -> None:
    client = _RecordingClient()
    r = Reasoner(backend="llama_cpp_server", client=client)
    _run(r.step(ReasoningInput(
        intent=_intent("GOTO", destination="Alcatraz", altitude=400),
        detections=[], frame_jpeg=None,
    )))
    user = client.chat_calls[0][1]
    # Could be a string or list-of-content (multimodal). Get text.
    if isinstance(user["content"], str):
        text = user["content"]
    else:
        text = user["content"][0].get("text", "")
    assert "Alcatraz" in text
    assert "400" in text


def test_search_user_prompt_includes_target_and_area() -> None:
    client = _RecordingClient()
    r = Reasoner(backend="llama_cpp_server", client=client)
    _run(r.step(ReasoningInput(
        intent=_intent("SEARCH", area="the harbor", target="small boats"),
        detections=[], frame_jpeg=None,
    )))
    user = client.chat_calls[0][1]
    text = user["content"] if isinstance(user["content"], str) else user["content"][0]["text"]
    assert "small boats" in text
    assert "the harbor" in text


def test_nl_context_appended_as_clarification() -> None:
    client = _RecordingClient()
    r = Reasoner(backend="llama_cpp_server", client=client)
    _run(r.step(ReasoningInput(
        intent=_intent("REPORT", nl_context="prioritize anything moving"),
        detections=[], frame_jpeg=None,
    )))
    user = client.chat_calls[0][1]
    text = user["content"] if isinstance(user["content"], str) else user["content"][0]["text"]
    assert "prioritize anything moving" in text


# ── Output parser handles the doctrine §8 format ─────────────────────────

def test_parser_extracts_cmd_reply_rationale() -> None:
    client = _RecordingClient(reply=(
        "CMD: GOTO location=\"Alcatraz\" altitude=400\n"
        "REPLY: WILCO\n"
        "RATIONALE: Transit to Alcatraz at 400 ft AGL."
    ))
    r = Reasoner(backend="llama_cpp_server", client=client)
    out = _run(r.step(ReasoningInput(intent=_intent("GOTO", destination="Alcatraz"), detections=[], frame_jpeg=None)))
    assert out.action["cmds"] == ["GOTO location=\"Alcatraz\" altitude=400"]
    assert out.action["reply"] == "WILCO"
    assert "WILCO" in out.decision
    assert "GOTO" in out.decision
    assert "400 ft AGL" in out.rationale


def test_parser_handles_unable_with_no_cmd() -> None:
    client = _RecordingClient(reply=(
        "REPLY: UNABLE reason=\"target ambiguous, specify coordinates\"\n"
        "RATIONALE: Cannot resolve the named landmark from current context."
    ))
    r = Reasoner(backend="llama_cpp_server", client=client)
    out = _run(r.step(ReasoningInput(intent=_intent("GOTO", destination="???"), detections=[], frame_jpeg=None)))
    assert out.action["cmds"] == []
    assert "UNABLE" in out.action["reply"]
    assert out.decision.startswith("UNABLE")


def test_parser_extracts_mavlink_for_motion_verb() -> None:
    """For GOTO/CLIMB/etc. the doctrine produces a MAVLINK: line — parsed separately
    and appended to the displayed rationale, with the raw JSON in action['mavlink']."""
    client = _RecordingClient(reply=(
        "CMD: GOTO location=\"Alcatraz\" altitude=400\n"
        "REPLY: WILCO\n"
        "RATIONALE: Transit north-west to Alcatraz Island and climb to 400 ft AGL on arrival. Route is clear of restricted operating zones.\n"
        "MAVLINK: {\"cmd\":\"MAV_CMD_NAV_WAYPOINT\",\"params\":{\"lat\":37.8270,\"lon\":-122.4230,\"alt_m\":122}}"
    ))
    r = Reasoner(backend="llama_cpp_server", client=client)
    out = _run(r.step(ReasoningInput(intent=_intent("GOTO", destination="Alcatraz"), detections=[], frame_jpeg=None)))
    assert out.action["cmds"] == ["GOTO location=\"Alcatraz\" altitude=400"]
    assert out.action["reply"] == "WILCO"
    assert out.action["mavlink"] is not None
    assert "MAV_CMD_NAV_WAYPOINT" in out.action["mavlink"]
    # Display rationale combines prose + MAVLink block (formatted with header).
    assert "Transit north-west" in out.rationale
    assert "MAV_CMD_NAV_WAYPOINT" in out.rationale
    assert "📡 MAVLINK" in out.rationale


def test_parser_no_mavlink_for_vision_verb() -> None:
    """SEARCH/REPORT/etc. should not produce a MAVLink block."""
    client = _RecordingClient(reply=(
        "REPLY: ROGER\n"
        "RATIONALE: Camera shows an indoor desk with a laptop and coffee cup. No vessels visible."
    ))
    r = Reasoner(backend="llama_cpp_server", client=client)
    out = _run(r.step(ReasoningInput(intent=_intent("REPORT"), detections=[], frame_jpeg=None)))
    assert out.action["mavlink"] is None
    assert "📡 MAVLINK" not in out.rationale


def test_parser_falls_back_when_format_drifts() -> None:
    client = _RecordingClient(reply="acknowledged the order\nwill comply with the search task")
    r = Reasoner(backend="llama_cpp_server", client=client)
    out = _run(r.step(ReasoningInput(intent=_intent("SEARCH", target="boats"), detections=[], frame_jpeg=None)))
    # No structured CMD/REPLY but we still produce a non-empty decision/rationale.
    assert out.decision
    assert out.rationale


# ── Frame attachment ──────────────────────────────────────────────────────

def test_frame_attached_when_available() -> None:
    """When FrameStore has a frame, it's attached to the user message as image_url."""
    client = _RecordingClient()
    store = _StubFrameStore(jpeg=b"FAKEJPEGDATA")
    r = Reasoner(backend="llama_cpp_server", client=client, frame_store=store)  # type: ignore[arg-type]
    _run(r.step(ReasoningInput(intent=_intent("REPORT"), detections=[], frame_jpeg=None)))
    user = client.chat_calls[0][1]
    assert isinstance(user["content"], list)
    image_part = next(p for p in user["content"] if p.get("type") == "image_url")
    assert "data:image/jpeg;base64," in image_part["image_url"]["url"]


def test_no_frame_means_text_only_user_content() -> None:
    """Without a frame, user message content is a plain string."""
    client = _RecordingClient()
    r = Reasoner(backend="llama_cpp_server", client=client)
    _run(r.step(ReasoningInput(intent=_intent("ABORT"), detections=[], frame_jpeg=None)))
    user = client.chat_calls[0][1]
    assert isinstance(user["content"], str)
