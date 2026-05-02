"""Envelope construction, parsing, and schema validation.

The shared JSON Schemas in shared/protocol/schemas/ are the source of truth.
Both encode and decode go through this module so we never put an invalid
message on the wire and never accept an invalid one off it.
"""

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


PROTOCOL_VERSION = "0.2.0"
PROTOCOL_MAJOR = "0"


_REPO_ROOT = Path(__file__).resolve().parents[4]
_SCHEMAS_DIR = _REPO_ROOT / "shared" / "protocol" / "schemas"


def _load_schema(name: str) -> dict[str, Any]:
    return json.loads((_SCHEMAS_DIR / name).read_text())


_envelope_validator = Draft202012Validator(_load_schema("envelope.schema.json"))
_command_validator = Draft202012Validator(_load_schema("command.schema.json"))
_telemetry_validator = Draft202012Validator(_load_schema("telemetry.schema.json"))


class ProtocolError(Exception):
    """Raised when a message fails schema or version checks."""


@dataclass
class Envelope:
    protocol_version: str
    message_id: str
    issued_at: str
    sender: str
    kind: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_message_id() -> str:
    return str(uuid.uuid4())


def encode_telemetry(sender: str, event: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Build, validate, and return a telemetry envelope ready for the wire."""
    payload = {"event": event, **fields}
    envelope = Envelope(
        protocol_version=PROTOCOL_VERSION,
        message_id=_new_message_id(),
        issued_at=_now_iso(),
        sender=sender,
        kind="telemetry",
        payload=payload,
    ).to_dict()
    validate(envelope)
    return envelope


def decode_command(raw: dict[str, Any]) -> Envelope:
    """Validate an inbound command envelope and return it as an Envelope."""
    validate(raw)
    if raw["kind"] != "command":
        raise ProtocolError(f"expected kind=command, got kind={raw['kind']}")
    return Envelope(
        protocol_version=raw["protocol_version"],
        message_id=raw["message_id"],
        issued_at=raw["issued_at"],
        sender=raw["sender"],
        kind=raw["kind"],
        payload=raw["payload"],
    )


def validate(envelope: dict[str, Any]) -> None:
    """Raise ProtocolError if the envelope or its payload is invalid."""
    errors = list(_envelope_validator.iter_errors(envelope))
    if errors:
        raise ProtocolError(f"envelope invalid: {errors[0].message}")

    version = envelope["protocol_version"]
    if version.split(".", 1)[0] != PROTOCOL_MAJOR:
        raise ProtocolError(
            f"protocol major mismatch: got {version}, this build speaks {PROTOCOL_VERSION}"
        )

    payload = envelope["payload"]
    kind = envelope["kind"]
    if kind == "command":
        payload_errors = list(_command_validator.iter_errors(payload))
    elif kind == "telemetry":
        payload_errors = list(_telemetry_validator.iter_errors(payload))
    else:
        raise ProtocolError(f"unknown kind: {kind}")
    if payload_errors:
        raise ProtocolError(f"{kind} payload invalid: {payload_errors[0].message}")
