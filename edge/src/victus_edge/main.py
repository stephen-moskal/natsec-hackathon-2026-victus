"""Edge node event loop.

Phase 1.0 wiring: two concurrent asyncio tasks share a single FoundryClient.

  - command_poller: every COMMAND_POLL_INTERVAL_S, calls pollCommands, logs
    each new command, immediately ACKs with result=ACCEPTED. The reasoner is
    not yet wired in — Phase 2 plugs into the same dispatch point.
  - telemetry_emitter: every POSITION_EMIT_INTERVAL_S, emits a Position
    heartbeat with mocked coordinates. Real GPS lands in Phase 2.

Run: `python -m victus_edge.main` (after `pip install -e .`).
"""

import asyncio
import logging

import structlog

from .comms.auth import TokenProvider
from .comms.foundry_client import FoundryClient
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


async def _command_poller(client: FoundryClient, cfg: Config) -> None:
    cursor: str | None = None
    while True:
        envelopes = await client.poll_commands(cursor)
        for env in envelopes:
            log.info(
                "command_received",
                message_id=env.message_id,
                verb=env.payload.get("verb"),
                params=env.payload.get("params"),
            )
            await client.ack_command(env.message_id, result="ACCEPTED")
            cursor = env.message_id
        await asyncio.sleep(cfg.command_poll_interval_s)


async def _telemetry_emitter(client: FoundryClient, cfg: Config) -> None:
    while True:
        envelope = encode_telemetry(
            sender=f"drone-{cfg.drone_id}",
            event="Position",
            fields={
                "lat": 42.3601,
                "lon": -71.0589,
                "alt_m": 100.0,
                "heading_deg": 90.0,
                "speed_mps": 0.0,
                "battery_pct": 95.0,
            },
        )
        await client.post_telemetry([envelope])
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


def run() -> None:
    """Entry point referenced by the `victus-edge` console script."""
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
