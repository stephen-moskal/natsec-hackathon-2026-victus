"""Envelope construction, parsing, and schema validation.

The shared JSON Schemas in shared/protocol/schemas/ are the source of truth.
Both encode and decode go through this module so that we never put an invalid
message on the wire and never accept an invalid one off it.
"""

from dataclasses import dataclass
from typing import Any


PROTOCOL_VERSION = "0.1.0"


@dataclass
class Envelope:
    protocol_version: str
    message_id: str
    issued_at: str       # ISO 8601 UTC
    sender: str
    kind: str            # "command" | "telemetry"
    payload: dict[str, Any]


def encode_telemetry(sender: str, event: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Build a telemetry envelope. To be implemented in Phase 1."""
    raise NotImplementedError


def decode_command(raw: dict[str, Any]) -> Envelope:
    """Validate against command.schema.json and return a typed envelope."""
    raise NotImplementedError


def validate(envelope: dict[str, Any]) -> None:
    """Raise if the envelope does not conform to its schema."""
    raise NotImplementedError
