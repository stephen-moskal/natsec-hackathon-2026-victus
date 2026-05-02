"""Runtime configuration loaded from environment variables.

Single source of truth for backend selection and credentials. All modules
import the loaded `Config` instance rather than reading os.environ directly,
so tests can substitute a fixture.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    drone_id: str
    foundry_base_url: str
    foundry_token: str
    llm_backend: str           # "llama_cpp_server" | "vllm" | "mock"
    llm_model_path: str | None
    vision_source: str         # "webcam:0" | "file:..." | "gst:..." | "mock"
    autonomy_backend: str      # "sitl" | "mock"
    telemetry_buffer_path: str
    log_level: str


def load() -> Config:
    """Read environment variables into a frozen Config. To be implemented."""
    raise NotImplementedError
