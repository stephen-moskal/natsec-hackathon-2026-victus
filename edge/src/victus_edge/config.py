"""Runtime configuration loaded from environment variables.

Single source of truth for backend selection and credentials. All modules
import the loaded `Config` instance rather than reading os.environ directly,
so tests can substitute a fixture.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    drone_id: str

    # Foundry endpoints — point at either real Foundry or the local stub.
    foundry_stack_url: str               # e.g. https://victus.usw-23.palantirfoundry.com
    foundry_telemetry_dataset_rid: str   # streaming dataset for raw_telemetry
    foundry_telemetry_view_rid: str | None  # optional but recommended for streams V2
    foundry_ontology: str                # ontology API name OR RID
    foundry_command_object_type: str     # API name of the command object type (e.g. "pzqmccug.command")

    foundry_auth_mode: str         # "STATIC" | "OAUTH"
    foundry_token: str | None      # used when auth_mode=STATIC
    foundry_oauth_token_url: str | None
    foundry_client_id: str | None
    foundry_client_secret: str | None

    llm_backend: str               # "llama_cpp_server" | "vllm" | "mock"
    llm_model_path: str | None
    vision_source: str             # "webcam:0" | "file:..." | "gst:..." | "mock"
    autonomy_backend: str          # "sitl" | "mock"

    telemetry_buffer_path: str
    command_poll_interval_s: float
    position_emit_interval_s: float
    log_level: str


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"required env var not set: {name}")
    return value


def load() -> Config:
    auth_mode = os.environ.get("FOUNDRY_AUTH_MODE", "STATIC").upper()
    if auth_mode not in ("STATIC", "OAUTH"):
        raise RuntimeError(f"FOUNDRY_AUTH_MODE must be STATIC or OAUTH, got {auth_mode}")

    foundry_token = os.environ.get("FOUNDRY_TOKEN")
    if auth_mode == "STATIC" and not foundry_token:
        raise RuntimeError("FOUNDRY_AUTH_MODE=STATIC requires FOUNDRY_TOKEN")

    if auth_mode == "OAUTH":
        for var in ("FOUNDRY_OAUTH_TOKEN_URL", "FOUNDRY_CLIENT_ID", "FOUNDRY_CLIENT_SECRET"):
            if not os.environ.get(var):
                raise RuntimeError(f"FOUNDRY_AUTH_MODE=OAUTH requires {var}")

    return Config(
        drone_id=_required("VICTUS_DRONE_ID"),
        foundry_stack_url=_required("FOUNDRY_STACK_URL").rstrip("/"),
        foundry_telemetry_dataset_rid=_required("FOUNDRY_TELEMETRY_DATASET_RID"),
        foundry_telemetry_view_rid=os.environ.get("FOUNDRY_TELEMETRY_VIEW_RID") or None,
        foundry_ontology=_required("FOUNDRY_ONTOLOGY"),
        foundry_command_object_type=_required("FOUNDRY_COMMAND_OBJECT_TYPE"),
        foundry_auth_mode=auth_mode,
        foundry_token=foundry_token,
        foundry_oauth_token_url=os.environ.get("FOUNDRY_OAUTH_TOKEN_URL"),
        foundry_client_id=os.environ.get("FOUNDRY_CLIENT_ID"),
        foundry_client_secret=os.environ.get("FOUNDRY_CLIENT_SECRET"),
        llm_backend=os.environ.get("VICTUS_LLM_BACKEND", "mock"),
        llm_model_path=os.environ.get("VICTUS_LLM_MODEL_PATH"),
        vision_source=os.environ.get("VICTUS_VISION_SOURCE", "mock"),
        autonomy_backend=os.environ.get("VICTUS_AUTONOMY_BACKEND", "mock"),
        telemetry_buffer_path=os.environ.get(
            "VICTUS_TELEMETRY_BUFFER_PATH", "./runtime/buffer.jsonl"
        ),
        command_poll_interval_s=float(os.environ.get("COMMAND_POLL_INTERVAL_S", "2.0")),
        position_emit_interval_s=float(os.environ.get("POSITION_EMIT_INTERVAL_S", "5.0")),
        log_level=os.environ.get("VICTUS_LOG_LEVEL", "INFO"),
    )
