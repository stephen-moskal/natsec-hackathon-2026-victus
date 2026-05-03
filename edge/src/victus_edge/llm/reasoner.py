"""On-board reasoning model.

Wraps a small VLM (Gemma 4 E4B-it or Qwen3-VL-2B-Instruct) running locally via
llama-server. Backend is selected by config; the `mock` backend returns
deterministic outputs for development without a model.

Inputs to a reasoning step:
  - the current intent (verb + params from the most recently accepted command)
  - the latest detections (from vision pipeline)
  - optionally the latest frame (for VLM backends)

Output:
  - a chosen action for the autonomy controller
  - a ReasoningTrace event for telemetry

Phase 1 keeps the action shape trivial (`{"do": "noop"}`) — the VLM's text
output is captured in `rationale` for inspection. Phase 2 will add structured
action parsing and a tactical-recon prompt template.
"""

from dataclasses import dataclass

from .http_client import LlamaCppClient


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


_DEFAULT_DESCRIBE_PROMPT = "Describe what you see in this image briefly."


class Reasoner:
    """Backend-agnostic reasoner interface.

    `client` is required for the `llama_cpp_server` backend and ignored by
    `mock`. It is not owned by the Reasoner — the caller is responsible for
    its lifecycle (typically constructed via runtime.factory).
    """

    def __init__(
        self,
        backend: str,
        client: LlamaCppClient | None = None,
        model_path: str | None = None,
    ) -> None:
        self.backend = backend
        self.client = client
        self.model_path = model_path
        if backend == "llama_cpp_server" and client is None:
            raise ValueError("llama_cpp_server backend requires a LlamaCppClient")

    async def step(self, inputs: ReasoningInput) -> ReasoningOutput:
        if self.backend == "mock":
            return ReasoningOutput(
                action={"do": "noop"},
                decision="mock",
                rationale="mock backend",
                tokens=0,
            )
        if self.backend == "llama_cpp_server":
            assert self.client is not None
            if inputs.frame_jpeg is None:
                raise ValueError("llama_cpp_server backend requires a frame_jpeg")
            text = await self.client.describe_frame(
                inputs.frame_jpeg, prompt=_DEFAULT_DESCRIBE_PROMPT
            )
            return ReasoningOutput(
                action={"do": "noop"},
                decision="describe",
                rationale=text[:500],
                tokens=0,
            )
        raise NotImplementedError(f"unknown reasoner backend: {self.backend}")
