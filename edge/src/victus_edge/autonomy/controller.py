"""Autonomy controller — translates reasoner actions into flight commands.

For the hackathon the `mock` backend simply logs and reports success. The
`sitl` backend speaks MAVLink to a PX4 or ArduPilot SITL instance, optionally
wrapped in Gazebo for visualization. Real flight is out of scope.

The reasoner emits abstract actions like `{"do": "goto", "lat": ..., "lon": ...}`
or `{"do": "loiter", "radius_m": 50}`; this module is responsible for any
translation to MAVLink primitives.
"""

from typing import Any


class AutonomyController:
    def __init__(self, backend: str) -> None:
        self.backend = backend

    async def execute(self, action: dict[str, Any]) -> bool:
        """Execute an action; return True on success. To be implemented in Phase 2."""
        raise NotImplementedError

    async def safe_fallback(self) -> None:
        """Hold position safely. Used when current intent expires."""
        raise NotImplementedError
