"""Edge node event loop.

Phase 1.0 wiring: two concurrent asyncio tasks share a single FoundryClient.

  - command_poller: every COMMAND_POLL_INTERVAL_S, calls pollCommands, logs
    each new command, immediately ACKs with result=WILCO. The reasoner is
    not yet wired in — Phase 2 plugs into the same dispatch point.
  - telemetry_emitter: every POSITION_EMIT_INTERVAL_S, emits a Position
    heartbeat with mocked coordinates. Real GPS lands in Phase 2.

Run: `python -m victus_edge.main` (after `pip install -e .`).
"""

import asyncio
import logging

import structlog

from .comms.auth import TokenProvider
from .comms.foundry_client import FoundryClient, FoundryEndpoints
from .comms.protocol import encode_telemetry
from .config import Config, load


log = structlog.get_logger(__name__)


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=level)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ]
    )


def _build_token_provider(cfg: Config) -> TokenProvider:
    if cfg.foundry_auth_mode == "STATIC":
        return TokenProvider(mode="STATIC", static_token=cfg.foundry_token)
    return TokenProvider(
        mode="OAUTH",
        oauth_token_url=cfg.foundry_oauth_token_url,
        client_id=cfg.foundry_client_id,
        client_secret=cfg.foundry_client_secret,
    )


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
    endpoints = FoundryEndpoints(
        stack_url=cfg.foundry_stack_url,
        telemetry_dataset_rid=cfg.foundry_telemetry_dataset_rid,
        telemetry_view_rid=cfg.foundry_telemetry_view_rid,
        ontology=cfg.foundry_ontology,
        command_object_type=cfg.foundry_command_object_type,
    )
    async with FoundryClient(
        token_provider=token_provider,
        endpoints=endpoints,
        drone_id=cfg.drone_id,
        buffer_path=cfg.telemetry_buffer_path,
    ) as client:
        await asyncio.gather(
            _command_poller(client, cfg),
            _telemetry_emitter(client, cfg),
        )


def run() -> None:
    """Entry point referenced by the `victus-edge` console script."""
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
