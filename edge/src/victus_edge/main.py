"""Edge node event loop.

Phase 1.0 wiring: two concurrent asyncio tasks share a single FoundryClient.

  - command_poller: every COMMAND_POLL_INTERVAL_S, calls pollCommands, logs
    each new command, immediately ACKs with result=ACCEPTED. The reasoner is
    not yet wired in — Phase 2 plugs into the same dispatch point.
  - telemetry_emitter: every POSITION_EMIT_INTERVAL_S, emits a Position
    heartbeat with mocked coordinates. Real GPS lands in Phase 2.

Run: `python -m victus_edge.main` (after `pip install -e .`).
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Any

import structlog

from .comms.auth import TokenProvider
from .comms.foundry_client import FoundryClient
from .comms.protocol import encode_telemetry
from .config import Config, load


log = structlog.get_logger(__name__)


_MODEL_TABLE: dict[str, tuple[str, str]] = {
    "gemma4": (
        "/opt/models/gemma4/gemma-4-E4B-it-Q4_K_M.gguf",
        "/opt/models/gemma4/mmproj-gemma-4-E4B-it-BF16.gguf",
    ),
    "qwen-vl": (
        "/opt/models/qwen3vl/Qwen3VL-2B-Instruct-Q4_K_M.gguf",
        "/opt/models/qwen3vl/mmproj-Qwen3VL-2B-Instruct-F16.gguf",
    ),
}

_DESCRIBE_PROMPT = "Describe what you see in this image briefly."


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=level)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="victus-edge",
        description="VICTUS edge node — drives llama-server + Foundry + optional webcam.",
    )
    p.add_argument(
        "--model",
        choices=sorted(_MODEL_TABLE.keys()),
        help="Model to launch. Maps to a hardcoded (model_path, mmproj_path) pair.",
    )
    p.add_argument("--model-path", help="Explicit GGUF path (overrides --model).")
    p.add_argument("--mmproj-path", help="Explicit mmproj GGUF path (overrides --model).")
    cam_group = p.add_mutually_exclusive_group()
    cam_group.add_argument(
        "--webcam",
        nargs="?",
        const=0,
        type=int,
        default=None,
        metavar="N",
        help="Open /dev/videoN via cv2 (CPU JPEG encode). Defaults to 0 if flag present without value.",
    )
    cam_group.add_argument(
        "--gst-webcam",
        nargs="?",
        const=0,
        type=int,
        default=None,
        metavar="N",
        help="Open /dev/videoN via GStreamer + Tegra hardware (nvvidconv + nvjpegenc). Jetson only.",
    )
    p.add_argument("--fps", type=float, default=None, help="Webcam capture cadence (default 1.0).")
    p.add_argument(
        "--test",
        action="store_true",
        help="Skip Foundry; print VLM descriptions of webcam frames to stdout.",
    )
    p.add_argument(
        "--no-llama-server",
        action="store_true",
        help="Don't spawn llama-server; assume one is already running.",
    )
    p.add_argument(
        "--llm-server-url",
        help="Base URL for llama-server (default http://127.0.0.1:8080).",
    )
    return p.parse_args(argv)


def _resolve_model_paths(args: argparse.Namespace) -> tuple[str | None, str | None]:
    """Apply CLI > table > env precedence. Returns (model_path, mmproj_path) or (None, None)."""
    model_path = args.model_path
    mmproj_path = args.mmproj_path

    if args.model and (model_path is None or mmproj_path is None):
        table_model, table_mmproj = _MODEL_TABLE[args.model]
        model_path = model_path or table_model
        mmproj_path = mmproj_path or table_mmproj

    return model_path, mmproj_path


def _build_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """Translate CLI args into Config field overrides."""
    overrides: dict[str, Any] = {}
    if args.test:
        overrides["test_mode"] = True
    if args.no_llama_server:
        overrides["manage_llama_server"] = False

    model_path, mmproj_path = _resolve_model_paths(args)
    if model_path:
        overrides["llm_model_path"] = model_path
    if mmproj_path:
        overrides["llm_mmproj_path"] = mmproj_path

    # Resolve the vision source: --gst-webcam wins if set, then --webcam, then
    # default to "webcam:0" (cv2) when --test is on but neither flag was passed.
    vision_active = False
    if args.gst_webcam is not None:
        overrides["vision_source"] = f"gst:{args.gst_webcam}"
        vision_active = True
    elif args.webcam is not None:
        overrides["vision_source"] = f"webcam:{args.webcam}"
        vision_active = True
    elif args.test:
        overrides["vision_source"] = "webcam:0"
        vision_active = True

    if args.fps is not None:
        overrides["vision_fps"] = args.fps

    if args.llm_server_url:
        overrides["llm_server_url"] = args.llm_server_url

    # llama-server backend is required when we're going to call describe_frame
    if args.test or vision_active:
        overrides["llm_backend"] = "llama_cpp_server"

    return overrides


# Verbs whose ACK should be ROGER (received & understood) rather than WILCO
# (acknowledged & will comply). Per drone_command_policy.json: REPORT is a
# read-only request — there's nothing to "comply" with.
_ROGER_VERBS: frozenset[str] = frozenset({"REPORT"})


def _ack_result_for(verb: str) -> str:
    return "ROGER" if verb in _ROGER_VERBS else "WILCO"


async def _command_poller(client: FoundryClient, cfg: Config) -> None:
    cursor: str | None = None
    while True:
        envelopes, invalid = await client.poll_commands(cursor)

        # Valid commands → log + ACK (WILCO or ROGER per verb).
        for env in envelopes:
            verb = env.payload.get("verb", "")
            log.info(
                "command_received",
                message_id=env.message_id,
                verb=verb,
                params=env.payload.get("params"),
            )
            await client.ack_command(env.message_id, result=_ack_result_for(verb))
            cursor = env.message_id

        # Invalid commands → ACK once with UNABLE so operator UI flips to REJECTED.
        # Per policy rule: "Unparseable commands return UNABLE with reason
        # 'command unclear, say again'."
        for ic in invalid:
            log.warning("acking_unable", message_id=ic.message_id, reason=ic.reason)
            await client.ack_command(
                ic.message_id,
                result="UNABLE",
                reason=ic.reason or "command unclear, say again",
            )

        await asyncio.sleep(cfg.command_poll_interval_s)


async def _telemetry_emitter(client: FoundryClient, cfg: Config) -> None:
    # Route: SF Ferry Terminal → Alcatraz, ~10 min at 5s emit cadence.
    _START_LAT, _START_LON = 37.7955, -122.3937   # Ferry Building / Embarcadero
    _END_LAT,   _END_LON   = 37.8270, -122.4230   # Alcatraz Island
    _STEPS = 120                                    # steps to complete the route
    _HEADING = 317.0                                # NW toward Alcatraz
    _SPEED_MPS = 5.0                                # ~10 knots
    _BATTERY_START = 95.0
    _BATTERY_END   = 72.0                           # drain to 72% by the time we arrive

    step = 0
    while True:
        t = min(step / _STEPS, 1.0)                 # clamp 0..1, hold at Alcatraz after
        lat = _START_LAT + t * (_END_LAT - _START_LAT)
        lon = _START_LON + t * (_END_LON - _START_LON)
        battery = _BATTERY_START + t * (_BATTERY_END - _BATTERY_START)
        speed = 0.0 if t >= 1.0 else _SPEED_MPS    # stop moving once arrived

        envelope = encode_telemetry(
            sender=f"drone-{cfg.drone_id}",
            event="Position",
            fields={
                "lat": round(lat, 6),
                "lon": round(lon, 6),
                "alt_m": 100.0,
                "heading_deg": _HEADING,
                "speed_mps": speed,
                "battery_pct": round(battery, 1),
            },
        )
        await client.post_telemetry([envelope])
        step += 1
        await asyncio.sleep(cfg.position_emit_interval_s)


async def run_async() -> None:
    cfg = load()
    _configure_logging(cfg.log_level)
    log.info("edge_starting", drone_id=cfg.drone_id, auth_mode=cfg.foundry_auth_mode)

    token_provider = _build_token_provider(cfg)
    async with FoundryClient(
        token_provider=token_provider,
        listener_url=cfg.foundry_listener_url,
        functions_url=cfg.foundry_functions_url,
        drone_id=cfg.drone_id,
        buffer_path=cfg.telemetry_buffer_path,
    ) as client:
        await asyncio.gather(
            _command_poller(client, cfg),
            _telemetry_emitter(client, cfg),
        )

    if cfg.manage_llama_server and cfg.llm_model_path:
        async with LlamaServer(cfg.llm_model_path, cfg.llm_mmproj_path):
            await _run_with_server()
    else:
        await _run_with_server()


async def run_async(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    overrides = _build_overrides(args)
    cfg = load(overrides=overrides)
    _configure_logging(cfg.log_level)

    log.info(
        "edge_starting",
        drone_id=cfg.drone_id,
        test_mode=cfg.test_mode,
        llm_backend=cfg.llm_backend,
        vision_source=cfg.vision_source,
        manage_llama_server=cfg.manage_llama_server,
    )

    if cfg.test_mode:
        await _run_test_mode(cfg)
    else:
        await _run_production_mode(cfg)


def run() -> None:
    """Entry point referenced by the `victus-edge` console script."""
    try:
        asyncio.run(run_async())
    except KeyboardInterrupt:
        log.info("edge_shutdown_signal")
        sys.exit(0)


if __name__ == "__main__":
    run()
