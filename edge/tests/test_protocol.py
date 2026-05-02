"""Schema round-trip + rejection tests for victus_edge.comms.protocol."""

import uuid

import pytest

from victus_edge.comms import protocol


def _valid_command_envelope() -> dict:
    return {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "message_id": str(uuid.uuid4()),
        "issued_at": "2026-05-02T18:00:00Z",
        "sender": "foundry-orchestrator",
        "kind": "command",
        "payload": {
            "drone_id": "uav-01",
            "verb": "HOLD",
            "priority": "ROUTINE",
            "expires_at": "2026-05-02T18:30:00Z",
            "params": {},
        },
    }


def test_encode_telemetry_round_trips_through_validate():
    env = protocol.encode_telemetry(
        sender="drone-uav-01",
        event="Position",
        fields={
            "lat": 42.36,
            "lon": -71.06,
            "alt_m": 100.0,
            "heading_deg": 0.0,
            "speed_mps": 0.0,
            "battery_pct": 100.0,
        },
    )
    protocol.validate(env)
    assert env["kind"] == "telemetry"
    assert env["protocol_version"] == protocol.PROTOCOL_VERSION
    assert env["payload"]["event"] == "Position"


def test_decode_command_returns_envelope():
    raw = _valid_command_envelope()
    decoded = protocol.decode_command(raw)
    assert decoded.payload["verb"] == "HOLD"
    assert decoded.kind == "command"


def test_decode_command_accepts_assign_mission_verb():
    raw = _valid_command_envelope()
    raw["payload"]["verb"] = "ASSIGN_MISSION"
    raw["payload"]["params"] = {
        "mission_id": "m-1",
        "name": "Recon Sector 7",
        "system_prompt": "Find target X and confirm location.",
    }
    decoded = protocol.decode_command(raw)
    assert decoded.payload["verb"] == "ASSIGN_MISSION"


def test_validate_rejects_unknown_verb():
    raw = _valid_command_envelope()
    raw["payload"]["verb"] = "TELEPORT"
    with pytest.raises(protocol.ProtocolError):
        protocol.validate(raw)


def test_validate_rejects_protocol_major_mismatch():
    raw = _valid_command_envelope()
    raw["protocol_version"] = "1.0.0"
    with pytest.raises(protocol.ProtocolError, match="protocol major mismatch"):
        protocol.validate(raw)


def test_validate_rejects_unknown_kind():
    raw = _valid_command_envelope()
    raw["kind"] = "gossip"
    with pytest.raises(protocol.ProtocolError):
        protocol.validate(raw)


def test_validate_rejects_command_payload_missing_required_field():
    raw = _valid_command_envelope()
    del raw["payload"]["priority"]
    with pytest.raises(protocol.ProtocolError):
        protocol.validate(raw)


def test_decode_command_rejects_telemetry_envelope():
    raw = _valid_command_envelope()
    raw["kind"] = "telemetry"
    raw["payload"] = {"event": "Status", "state": "NOMINAL"}
    with pytest.raises(protocol.ProtocolError, match="expected kind=command"):
        protocol.decode_command(raw)
