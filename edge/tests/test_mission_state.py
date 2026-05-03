"""Tests for the on-board MissionState tracker."""

from dataclasses import dataclass

from victus_edge.llm.mission_state import MissionState


@dataclass
class _StubEnvelope:
    payload: dict


def test_initial_state_is_empty() -> None:
    s = MissionState()
    assert s.current is None
    assert s.context_block() == ""


def test_assign_mission_captures_fields() -> None:
    s = MissionState()
    s.update_from_command(
        _StubEnvelope(payload={
            "verb": "ASSIGN_MISSION",
            "params": {
                "mission_id": "abc12345-6789-0000-aaaa-bbbbccccdddd",
                "name": "Harbor Recon",
                "system_prompt": "Scan the harbor for boats and report any contact.",
            },
        })
    )
    assert s.current is not None
    assert s.current.name == "Harbor Recon"
    assert s.current.system_prompt.startswith("Scan the harbor")
    block = s.context_block()
    assert "Harbor Recon" in block
    assert "Scan the harbor" in block


def test_non_mission_verbs_are_ignored() -> None:
    s = MissionState()
    s.update_from_command(_StubEnvelope(payload={"verb": "REPORT", "params": {}}))
    assert s.current is None


def test_partial_assign_mission_ignored() -> None:
    s = MissionState()
    # missing system_prompt
    s.update_from_command(
        _StubEnvelope(payload={
            "verb": "ASSIGN_MISSION",
            "params": {"mission_id": "x", "name": "y"},
        })
    )
    assert s.current is None


def test_subsequent_assignment_overwrites() -> None:
    s = MissionState()
    base = {
        "verb": "ASSIGN_MISSION",
        "params": {"mission_id": "id-1", "name": "First", "system_prompt": "do thing 1"},
    }
    s.update_from_command(_StubEnvelope(payload=base))
    base["params"]["mission_id"] = "id-2"
    base["params"]["name"] = "Second"
    base["params"]["system_prompt"] = "do thing 2"
    s.update_from_command(_StubEnvelope(payload=base))
    assert s.current is not None
    assert s.current.name == "Second"
    assert "do thing 2" in s.current.system_prompt
