"""Verb-dispatch tests for the Reasoner.

We mock LlamaCppClient at the method level so we can assert which path
(`describe_frame` vs `chat_completion`) was taken for each verb category,
and inspect the prompt string the reasoner built.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest

from victus_edge.llm.mission_state import MissionState
from victus_edge.llm.reasoner import Reasoner, ReasoningInput


class _StubFrameStore:
    """Minimal stand-in for vision.frame_server.FrameStore."""

    def __init__(self, jpeg: bytes | None = None) -> None:
        self._jpeg = jpeg

    def get(self) -> bytes | None:
        return self._jpeg


class _RecordingClient:
    """LlamaCppClient stand-in that records which methods were called."""

    def __init__(self, reply: str = "DECISION: ok\nRATIONALE: stub reply") -> None:
        self.reply = reply
        self.describe_calls: list[tuple[bytes, str]] = []
        self.chat_calls: list[list[dict]] = []

    async def describe_frame(self, jpeg: bytes, prompt: str, **_: Any) -> str:
        self.describe_calls.append((jpeg, prompt))
        return self.reply

    async def chat_completion(self, messages: list[dict], **_: Any) -> str:
        self.chat_calls.append(messages)
        return self.reply


def _intent(verb: str, **params: Any) -> dict:
    return {"verb": verb, "params": params, "priority": "ROUTINE"}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Mock backend stays deterministic ──────────────────────────────────────

def test_mock_backend_returns_mock_decision() -> None:
    r = Reasoner(backend="mock")
    out = _run(r.step(ReasoningInput(intent=_intent("REPORT"), detections=[], frame_jpeg=None)))
    assert out.decision == "mock-report"
    assert "mock backend" in out.rationale


# ── Vision verbs use describe_frame when a frame is available ─────────────

@pytest.mark.parametrize("verb", ["REPORT", "SEARCH", "OBSERVE", "TRACK", "IDENTIFY"])
def test_vision_verb_with_frame_uses_describe(verb: str) -> None:
    client = _RecordingClient(reply="DECISION: see\nRATIONALE: I see a thing.")
    store = _StubFrameStore(jpeg=b"FAKEJPEG")
    r = Reasoner(backend="llama_cpp_server", client=client, frame_store=store)  # type: ignore[arg-type]
    out = _run(r.step(ReasoningInput(intent=_intent(verb, target="boat"), detections=[], frame_jpeg=None)))
    assert len(client.describe_calls) == 1
    assert len(client.chat_calls) == 0
    sent_jpeg, sent_prompt = client.describe_calls[0]
    assert sent_jpeg == b"FAKEJPEG"
    assert verb in sent_prompt
    assert out.decision == "see"


# ── Vision verbs without a frame fall back to text-only with a note ──────

def test_vision_verb_without_frame_falls_back_to_chat() -> None:
    client = _RecordingClient()
    store = _StubFrameStore(jpeg=None)
    r = Reasoner(backend="llama_cpp_server", client=client, frame_store=store)  # type: ignore[arg-type]
    _run(r.step(ReasoningInput(intent=_intent("REPORT"), detections=[], frame_jpeg=None)))
    assert len(client.describe_calls) == 0
    assert len(client.chat_calls) == 1
    # The fallback prompt explicitly notes no frame is available.
    assert "No live camera frame" in client.chat_calls[0][-1]["content"]


# ── Motion verbs use chat with MAVLink-output prompt ─────────────────────

@pytest.mark.parametrize("verb", ["GOTO", "ALTITUDE", "LOITER"])
def test_motion_verb_uses_chat_with_mavlink_prompt(verb: str) -> None:
    client = _RecordingClient(
        reply='DECISION: navigate\nRATIONALE: ```json\n{"mavlink_cmd":"MAV_CMD_NAV_WAYPOINT"}\n```'
    )
    r = Reasoner(backend="llama_cpp_server", client=client)
    _run(r.step(ReasoningInput(intent=_intent(verb, destination="Alcatraz"), detections=[], frame_jpeg=None)))
    assert len(client.describe_calls) == 0
    assert len(client.chat_calls) == 1
    user_msg = client.chat_calls[0][-1]["content"]
    assert "MAVLink" in user_msg
    assert verb in user_msg


# ── Safety verbs use chat with simple acknowledgment prompt ──────────────

@pytest.mark.parametrize("verb", ["ABORT", "RTB"])
def test_safety_verb_uses_chat_acknowledgment(verb: str) -> None:
    client = _RecordingClient()
    r = Reasoner(backend="llama_cpp_server", client=client)
    _run(r.step(ReasoningInput(intent=_intent(verb), detections=[], frame_jpeg=None)))
    assert len(client.describe_calls) == 0
    assert len(client.chat_calls) == 1
    assert "halt" in client.chat_calls[0][-1]["content"].lower() or "return" in client.chat_calls[0][-1]["content"].lower()


# ── Mission context flows into the prompt ────────────────────────────────

def test_active_mission_appears_in_prompt_header() -> None:
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
            "system_prompt": "Scan the harbor and report contacts.",
        },
    }))

    r = Reasoner(backend="llama_cpp_server", client=client, mission_state=ms)
    _run(r.step(ReasoningInput(intent=_intent("REPORT"), detections=[], frame_jpeg=None)))
    sent = client.chat_calls[0][-1]["content"]
    assert "Recon Sector 7" in sent
    assert "Scan the harbor" in sent


# ── nl_context flows into the prompt ─────────────────────────────────────

def test_nl_context_in_prompt() -> None:
    client = _RecordingClient()
    r = Reasoner(backend="llama_cpp_server", client=client)
    _run(r.step(ReasoningInput(
        intent=_intent("REPORT", nl_context="describe what you see right now"),
        detections=[], frame_jpeg=None,
    )))
    sent = client.chat_calls[0][-1]["content"]
    assert "describe what you see right now" in sent
