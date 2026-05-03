"""Schema round-trip + rejection tests for victus_edge.comms.protocol.

Aligned with drone_command_policy.json (protocol 0.3.0+).
"""

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
            "verb": "ABORT",
            "priority": "IMMEDIATE",
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
    assert decoded.payload["verb"] == "ABORT"
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


@pytest.mark.parametrize(
    "verb,params",
    [
        ("RTB", {}),
        ("GOTO", {"destination": "the lighthouse"}),
        ("ALTITUDE", {"direction": "CLIMB", "altitude": 400}),
        ("LOITER", {"duration": "PT10M"}),
        ("SEARCH", {"area": "the harbor", "target": "small boats"}),
        ("OBSERVE", {"target": "that pier", "duration": "PT10M", "reportInterval": "PT60S"}),
        ("REPORT", {"subject": "current scene"}),
        ("TRACK", {"target": "the white truck", "standOffMeters": 30}),
        ("IDENTIFY", {"target": "the vessel at the pier"}),
    ],
)
def test_decode_command_accepts_all_policy_verbs(verb: str, params: dict):
    raw = _valid_command_envelope()
    raw["payload"]["verb"] = verb
    raw["payload"]["params"] = params
    decoded = protocol.decode_command(raw)
    assert decoded.payload["verb"] == verb


def test_validate_rejects_unknown_verb():
    raw = _valid_command_envelope()
    raw["payload"]["verb"] = "TELEPORT"
    with pytest.raises(protocol.ProtocolError):
        protocol.validate(raw)


def test_validate_rejects_old_pre_policy_verbs():
    """HOLD/SCAN/INVESTIGATE/FOLLOW were retired in 0.3.0 in favor of policy verbs."""
    raw = _valid_command_envelope()
    for old in ("HOLD", "SCAN", "INVESTIGATE", "FOLLOW"):
        raw["payload"]["verb"] = old
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


def test_command_ack_uses_brevity_terms():
    """CommandAck.result uses drone brevity replies (WILCO/UNABLE/...) per policy 0.3.0."""
    env = protocol.encode_telemetry(
        sender="drone-uav-01",
        event="CommandAck",
        fields={"command_id": "abc", "result": "WILCO"},
    )
    protocol.validate(env)


def test_command_ack_rejects_old_accepted_term():
    """The pre-0.3.0 'ACCEPTED' result is no longer in the enum."""
    raw = {
        "protocol_version": protocol.PROTOCOL_VERSION,
        "message_id": str(uuid.uuid4()),
        "issued_at": "2026-05-02T18:00:00Z",
        "sender": "drone-uav-01",
        "kind": "telemetry",
        "payload": {"event": "CommandAck", "command_id": "abc", "result": "ACCEPTED"},
    }
    with pytest.raises(protocol.ProtocolError):
        protocol.validate(raw)


def test_sitrep_event_validates():
    env = protocol.encode_telemetry(
        sender="drone-uav-01",
        event="Sitrep",
        fields={
            "observed_at": "2026-05-02T18:00:00Z",
            "location": {"lat": 42.36, "lon": -71.06},
            "scene": "Calm harbor, two small boats moored to the east pier.",
            "contacts": [],
            "link_state": "CONNECTED",
        },
    )
    protocol.validate(env)


def test_bingo_event_validates():
    env = protocol.encode_telemetry(
        sender="drone-uav-01",
        event="Bingo",
        fields={"resource": "fuel", "remaining_pct": 12.5},
    )
    protocol.validate(env)
