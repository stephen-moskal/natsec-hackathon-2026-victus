"""On-board reasoning model.

Wraps a small VLM (Gemma 3 4B IT or Qwen2.5-VL-7B) running locally via
llama.cpp server or vLLM. Backend is selected by config; a `mock` backend
returns deterministic outputs for development without a model.

Inputs to a reasoning step:
  - the current intent (verb + params from the most recently accepted command)
  - the latest detections (from vision pipeline)
  - optionally the latest frame (for VLM backends)

Output:
  - a chosen action for the autonomy controller
  - a ReasoningTrace event for telemetry
"""

from dataclasses import dataclass


@dataclass
class ReasoningInput:
    intent: dict           # current command payload
    detections: list[dict] # recent vision detections
    frame_jpeg: bytes | None


@dataclass
class ReasoningOutput:
    action: dict           # autonomy-controller action
    decision: str          # short label, e.g. "approach_target"
    rationale: str         # short natural-language explanation, <= 500 chars
    tokens: int


class Reasoner:
    """Backend-agnostic reasoner interface."""

    def __init__(self, backend: str, model_path: str | None) -> None:
        self.backend = backend
        self.model_path = model_path

    async def step(self, inputs: ReasoningInput) -> ReasoningOutput:
        """Run one reasoning step. To be implemented in Phase 2."""
        raise NotImplementedError
