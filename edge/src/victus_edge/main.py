"""Edge node entrypoint.

Single supervisor process for the Jetson container. Owns:

  * a llama-server child process (via `LlamaServer`)
  * optionally a USB webcam (`WebcamSource` / `GstSource`)
  * optionally a Foundry comms client (`FoundryClient`) — produces
    poll/telemetry/frame-server traffic in production mode

CLI flags switch between modes:

  --model {gemma4|qwen-vl}   pick the GGUF + mmproj paths to launch
  --model-path PATH          override model path explicitly
  --mmproj-path PATH         override mmproj path explicitly
  --webcam [N]               open /dev/videoN (default 0 if flag present)
  --gst-webcam [N]           open /dev/videoN via Tegra GStreamer
  --fps F                    webcam capture cadence (default 1.0)
  --test                     skip Foundry, print VLM descriptions of frames
  --no-llama-server          assume llama-server is already running externally
  --llm-server-url URL       base URL for llama-server (default 127.0.0.1:8080)

Resolution order for model paths: --model-path/--mmproj-path > --model
(table) > env vars baked into the Docker image.

Production mode runs three concurrent asyncio tasks that share a FoundryClient:

  - _command_poller: polls Foundry for PENDING commands, logs each, ACKs with
    WILCO (or ROGER for read-only verbs like REPORT). Schema-invalid commands
    get an UNABLE ACK so the operator UI flips to REJECTED.
  - _telemetry_emitter: emits a Position heartbeat each tick along a scripted
    SF→Alcatraz route (mocked GPS for the demo).
  - run_frame_server: serves the latest webcam JPEG over local HTTP for the
    BFF, and publishes FrameThumbnail telemetry events to Foundry.

Test mode (--test) runs only the VLM describe loop against the webcam and
prints captions to stdout — no Foundry traffic.
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone
from typing import Any

import structlog

from .comms.foundry_client import FoundryClient
from .comms.protocol import encode_telemetry
from .config import Config, load
from .llm.http_client import LlamaCppClient
from .llm.mission_state import MissionState
from .llm.reasoner import Reasoner, ReasoningInput
from .llm.reasoning_server import ReasoningStore, run_reasoning_server
from .llm.server import LlamaServer
from .runtime.factory import build_foundry_client, build_vision
from .vision.frame_server import FrameStore, run_frame_server
from .vision.pipeline import GstSource, WebcamSource


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


# Verbs whose ACK should be ROGER (received & understood) rather than WILCO
# (acknowledged & will comply). Per drone_command_policy.json: REPORT is a
# read-only request — there's nothing to "comply" with.
_ROGER_VERBS: frozenset[str] = frozenset({"REPORT"})


def _ack_result_for(verb: str) -> str:
    return "ROGER" if verb in _ROGER_VERBS else "WILCO"


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


async def _command_poller(
    client: FoundryClient,
    cfg: Config,
    reasoner: Reasoner | None = None,
    reasoning_store: ReasoningStore | None = None,
    mission_state: MissionState | None = None,
) -> None:
    cursor: str | None = None
    while True:
        envelopes, invalid = await client.poll_commands(cursor)

        # Valid commands → log + ACK + (if LLM is wired) reason and publish.
        for env in envelopes:
            verb = env.payload.get("verb", "")
            log.info(
                "command_received",
                message_id=env.message_id,
                verb=verb,
                params=env.payload.get("params"),
            )
            # ACK first so the operator UI flips to ACKED quickly, before
            # any (potentially multi-second) LLM inference.
            await client.ack_command(env.message_id, result=_ack_result_for(verb))
            cursor = env.message_id

            # Update mission state BEFORE the reasoner runs so ASSIGN_MISSION
            # commands have their own mission in scope, and subsequent verbs
            # see the most recent mission as context.
            if mission_state is not None:
                mission_state.update_from_command(env)

            # Run the reasoner inline if configured. Failures are logged but
            # don't crash the poller — next command still gets a chance.
            if reasoner is not None:
                try:
                    reasoning = await reasoner.step(
                        ReasoningInput(intent=env.payload, detections=[], frame_jpeg=None)
                    )
                    log.info(
                        "reasoning_step",
                        message_id=env.message_id,
                        verb=verb,
                        decision=reasoning.decision,
                        rationale=reasoning.rationale,
                        tokens=reasoning.tokens,
                    )
                    # 1) Push to the local HTTP store for live UI display.
                    if reasoning_store is not None:
                        reasoning_store.put(
                            command_id=env.message_id,
                            verb=verb,
                            decision=reasoning.decision,
                            rationale=reasoning.rationale,
                            tokens=reasoning.tokens,
                        )
                    # 2) Publish ReasoningTrace to Foundry for permanent storage.
                    trace = encode_telemetry(
                        sender=f"drone-{cfg.drone_id}",
                        event="ReasoningTrace",
                        fields={
                            "command_id": env.message_id,
                            "decision": reasoning.decision,
                            "rationale": reasoning.rationale[:500],
                            "tokens": reasoning.tokens,
                        },
                    )
                    await client.post_telemetry([trace])
                except Exception as exc:                       # noqa: BLE001
                    log.error(
                        "reasoning_failed",
                        message_id=env.message_id,
                        verb=verb,
                        error=str(exc),
                    )

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


async def _describe_loop(webcam: WebcamSource | GstSource, llm: LlamaCppClient) -> None:
    """Read frames, send to llama-server, print descriptions. Used in --test mode."""
    frame_idx = 0
    async for jpeg in webcam.frames():
        frame_idx += 1
        try:
            description = await llm.describe_frame(jpeg, prompt=_DESCRIBE_PROMPT)
        except Exception as exc:
            log.error("describe_frame_failed", frame_idx=frame_idx, error=str(exc))
            continue
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        # stdout (not structlog) so the description is the primary visible output
        print(f"[{ts}] frame={frame_idx} description={description.strip()}", flush=True)


async def _run_test_mode(cfg: Config) -> None:
    """--test path: llama-server (optional) + webcam → VLM → print loop."""
    webcam = build_vision(cfg)
    if webcam is None:
        raise RuntimeError(
            "--test requires a webcam source; pass --webcam N or set VICTUS_VISION_SOURCE=webcam:N"
        )

    if cfg.manage_llama_server:
        if not cfg.llm_model_path:
            raise RuntimeError(
                "no model path resolved — pass --model {gemma4|qwen-vl} or --model-path PATH"
            )
        async with LlamaServer(cfg.llm_model_path, cfg.llm_mmproj_path) as server:
            async with LlamaCppClient(server.base_url, timeout_s=120.0) as client:
                await _describe_loop(webcam, client)
    else:
        async with LlamaCppClient(cfg.llm_server_url, timeout_s=120.0) as client:
            await _describe_loop(webcam, client)


async def _run_production_mode(cfg: Config) -> None:
    """Default path: optionally spawn llama-server, run Foundry poller + emitter + frame + reasoning servers."""
    foundry = build_foundry_client(cfg)
    assert foundry is not None, "production mode requires a Foundry client"

    # Shared state across the running tasks — built up-front so the
    # Reasoner, frame server, and command poller all see the same instances.
    frame_store = FrameStore()
    mission_state = MissionState()

    # Reasoner is wired only when the LLM backend is non-mock. Caller controls
    # this via VICTUS_LLM_BACKEND=llama_cpp_server (typical) or "mock".
    async def _run_with_server() -> None:
        reasoner: Reasoner | None = None
        reasoning_store: ReasoningStore | None = None
        llm_client_ctx: LlamaCppClient | None = None

        if cfg.llm_backend == "llama_cpp_server":
            llm_client_ctx = LlamaCppClient(cfg.llm_server_url, timeout_s=60.0)
            await llm_client_ctx.__aenter__()
            reasoner = Reasoner(
                backend=cfg.llm_backend,
                client=llm_client_ctx,
                frame_store=frame_store,
                mission_state=mission_state,
            )
            reasoning_store = ReasoningStore()
            log.info("reasoner_wired", backend=cfg.llm_backend, url=cfg.llm_server_url)
        elif cfg.llm_backend == "mock":
            reasoner = Reasoner(
                backend="mock",
                frame_store=frame_store,
                mission_state=mission_state,
            )
            reasoning_store = ReasoningStore()
            log.info("reasoner_wired", backend="mock")

        try:
            async with foundry as client:
                tasks = [
                    _command_poller(client, cfg, reasoner, reasoning_store, mission_state),
                    _telemetry_emitter(client, cfg),
                    run_frame_server(client, cfg, frame_store),
                ]
                if reasoning_store is not None:
                    tasks.append(run_reasoning_server(reasoning_store))
                await asyncio.gather(*tasks)
        finally:
            if llm_client_ctx is not None:
                await llm_client_ctx.__aexit__(None, None, None)

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
