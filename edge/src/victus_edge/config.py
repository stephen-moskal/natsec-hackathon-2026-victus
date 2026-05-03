"""Runtime configuration loaded from environment variables.

Single source of truth for backend selection and credentials. All modules
import the loaded `Config` instance rather than reading os.environ directly,
so tests can substitute a fixture.

CLI args layer over env via the `overrides` parameter to `load()`; values in
the overrides dict (keyed by Config field name) win over os.environ. Setting
`overrides["test_mode"]=True` relaxes STATIC token validation and treats
Foundry endpoints as optional — used by main.py's `--test` mode, where the
process runs the VLM/webcam loop without any Foundry traffic.
"""

import os
from dataclasses import dataclass
from typing import Any


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
    llm_mmproj_path: str | None    # vision projector for multimodal models
    llm_server_url: str            # base URL of llama-server

    vision_source: str               # "webcam:N" | "gst:N" | "file:..." | "mock"
    webcam_device_index: int | None  # parsed from vision_source when "webcam:N"
    gst_device_index: int | None     # parsed from vision_source when "gst:N"
    vision_fps: float

    autonomy_backend: str          # "sitl" | "mock"

    telemetry_buffer_path: str
    command_poll_interval_s: float
    position_emit_interval_s: float
    log_level: str

    test_mode: bool                # skip Foundry comms; print VLM output
    manage_llama_server: bool      # spawn llama-server subprocess from main.py


def _required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"required env var not set: {name}")
    return value


def _parse_webcam_index(source: str) -> int | None:
    """Extract N from 'webcam:N'. Returns None for non-webcam sources."""
    if not source.startswith("webcam:"):
        return None
    try:
        return int(source.split(":", 1)[1])
    except (ValueError, IndexError):
        return None


def _parse_gst_index(source: str) -> int | None:
    """Extract N from 'gst:N'. Returns None for non-gst sources."""
    if not source.startswith("gst:"):
        return None
    try:
        return int(source.split(":", 1)[1])
    except (ValueError, IndexError):
        return None


def load(overrides: dict[str, Any] | None = None) -> Config:
    """Load Config from env, with optional dict overrides keyed by Config field name.

    `overrides` lets the CLI inject values without monkey-patching os.environ.
    Set `overrides["test_mode"]=True` to skip Foundry credential validation —
    the foundry_* fields fall back to empty strings since main.py won't
    construct a FoundryClient in test mode.
    """
    o = overrides or {}
    test_mode = bool(o.get("test_mode", False))

    def pick(field: str, env_key: str, default: str | None = None) -> str | None:
        if field in o and o[field] is not None:
            return o[field]
        return os.environ.get(env_key, default)

    auth_mode = (pick("foundry_auth_mode", "FOUNDRY_AUTH_MODE", "STATIC") or "STATIC").upper()
    if auth_mode not in ("STATIC", "OAUTH"):
        raise RuntimeError(f"FOUNDRY_AUTH_MODE must be STATIC or OAUTH, got {auth_mode}")

    foundry_token = pick("foundry_token", "FOUNDRY_TOKEN")
    if not test_mode:
        if auth_mode == "STATIC" and not foundry_token:
            raise RuntimeError("FOUNDRY_AUTH_MODE=STATIC requires FOUNDRY_TOKEN")
        if auth_mode == "OAUTH":
            for field, var in (
                ("foundry_oauth_token_url", "FOUNDRY_OAUTH_TOKEN_URL"),
                ("foundry_client_id", "FOUNDRY_CLIENT_ID"),
                ("foundry_client_secret", "FOUNDRY_CLIENT_SECRET"),
            ):
                if not (o.get(field) or os.environ.get(var)):
                    raise RuntimeError(f"FOUNDRY_AUTH_MODE=OAUTH requires {var}")

    drone_id = pick("drone_id", "VICTUS_DRONE_ID") or (
        "test-drone" if test_mode else _required("VICTUS_DRONE_ID")
    )
    foundry_stack_url = (pick("foundry_stack_url", "FOUNDRY_STACK_URL") or (
        "" if test_mode else _required("FOUNDRY_STACK_URL")
    )).rstrip("/")
    foundry_telemetry_dataset_rid = pick(
        "foundry_telemetry_dataset_rid", "FOUNDRY_TELEMETRY_DATASET_RID"
    ) or ("" if test_mode else _required("FOUNDRY_TELEMETRY_DATASET_RID"))
    foundry_telemetry_view_rid = pick(
        "foundry_telemetry_view_rid", "FOUNDRY_TELEMETRY_VIEW_RID"
    ) or None
    foundry_ontology = pick("foundry_ontology", "FOUNDRY_ONTOLOGY") or (
        "" if test_mode else _required("FOUNDRY_ONTOLOGY")
    )
    foundry_command_object_type = pick(
        "foundry_command_object_type", "FOUNDRY_COMMAND_OBJECT_TYPE"
    ) or ("" if test_mode else _required("FOUNDRY_COMMAND_OBJECT_TYPE"))

    vision_source = pick("vision_source", "VICTUS_VISION_SOURCE", "mock") or "mock"

    return Config(
        drone_id=drone_id,
        foundry_stack_url=foundry_stack_url,
        foundry_telemetry_dataset_rid=foundry_telemetry_dataset_rid,
        foundry_telemetry_view_rid=foundry_telemetry_view_rid,
        foundry_ontology=foundry_ontology,
        foundry_command_object_type=foundry_command_object_type,
        foundry_auth_mode=auth_mode,
        foundry_token=foundry_token,
        foundry_oauth_token_url=pick("foundry_oauth_token_url", "FOUNDRY_OAUTH_TOKEN_URL"),
        foundry_client_id=pick("foundry_client_id", "FOUNDRY_CLIENT_ID"),
        foundry_client_secret=pick("foundry_client_secret", "FOUNDRY_CLIENT_SECRET"),
        llm_backend=pick("llm_backend", "VICTUS_LLM_BACKEND", "mock") or "mock",
        llm_model_path=pick("llm_model_path", "VICTUS_LLM_MODEL_PATH"),
        llm_mmproj_path=pick("llm_mmproj_path", "VICTUS_LLM_MMPROJ_PATH"),
        llm_server_url=pick(
            "llm_server_url", "VICTUS_LLM_SERVER_URL", "http://127.0.0.1:8080"
        ) or "http://127.0.0.1:8080",
        vision_source=vision_source,
        webcam_device_index=_parse_webcam_index(vision_source),
        gst_device_index=_parse_gst_index(vision_source),
        vision_fps=float(
            o.get("vision_fps") if o.get("vision_fps") is not None
            else os.environ.get("VICTUS_VISION_FPS", "1.0")
        ),
        autonomy_backend=pick("autonomy_backend", "VICTUS_AUTONOMY_BACKEND", "mock") or "mock",
        telemetry_buffer_path=pick(
            "telemetry_buffer_path",
            "VICTUS_TELEMETRY_BUFFER_PATH",
            "./runtime/buffer.jsonl",
        ) or "./runtime/buffer.jsonl",
        command_poll_interval_s=float(
            o.get("command_poll_interval_s") if o.get("command_poll_interval_s") is not None
            else os.environ.get("COMMAND_POLL_INTERVAL_S", "2.0")
        ),
        position_emit_interval_s=float(
            o.get("position_emit_interval_s") if o.get("position_emit_interval_s") is not None
            else os.environ.get("POSITION_EMIT_INTERVAL_S", "5.0")
        ),
        log_level=pick("log_level", "VICTUS_LOG_LEVEL", "INFO") or "INFO",
        test_mode=test_mode,
        manage_llama_server=bool(o.get("manage_llama_server", True)),
    )
