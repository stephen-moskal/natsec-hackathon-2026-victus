"""Edge node event loop.

Owns the intent state machine. Coordinates vision, reasoner, autonomy, and
comms via asyncio queues. Applies command expiry and falls back to HOLD when
the current intent expires or is aborted.

Run: `python -m victus_edge.main` (after `pip install -e .`).
"""

import asyncio


async def run_async() -> None:
    """Wire modules together and run the event loop. To be implemented in Phase 1."""
    raise NotImplementedError


def run() -> None:
    """Entry point referenced by the `victus-edge` console script."""
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
