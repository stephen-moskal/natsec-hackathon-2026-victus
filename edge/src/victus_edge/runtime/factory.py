"""Backend factories — string-discriminator dispatch for vision/LLM/Foundry.

main.py calls factory.build_*(cfg) instead of branching on backend strings
itself. This keeps backend-specific instantiation (auth providers, URL
parsing, optional dep checks) out of the orchestration code.

Each factory accepts the loaded Config and returns either a constructed
client/source or None when the backend is "mock" / off.
"""

from ..comms.auth import TokenProvider
from ..comms.foundry_client import FoundryClient, FoundryEndpoints
from ..config import Config
from ..llm.http_client import LlamaCppClient
from ..vision.pipeline import GstSource, WebcamSource


def build_vision(cfg: Config) -> WebcamSource | GstSource | None:
    """Dispatch on cfg.vision_source. None for 'mock' / unsupported.

    Order matters: gst is checked before webcam so a `gst:N` source string
    routes to the Tegra hardware path even though both share the device
    index N. File-based sources are recognized in cfg.vision_source but not
    yet implemented as readers — they fall through to None.
    """
    if cfg.gst_device_index is not None:
        return GstSource(cfg.gst_device_index, fps=cfg.vision_fps)
    if cfg.webcam_device_index is not None:
        return WebcamSource(cfg.webcam_device_index, fps=cfg.vision_fps)
    return None


def build_llm_client(cfg: Config) -> LlamaCppClient:
    """Construct a LlamaCppClient pointed at cfg.llm_server_url.

    Always returns a client. Whether the harness actually calls it is decided
    by the Reasoner backend dispatch (mock backend never calls).
    """
    return LlamaCppClient(cfg.llm_server_url)


def build_foundry_client(cfg: Config) -> FoundryClient | None:
    """Construct a FoundryClient unless cfg.test_mode is set."""
    if cfg.test_mode:
        return None
    endpoints = FoundryEndpoints(
        stack_url=cfg.foundry_stack_url,
        telemetry_dataset_rid=cfg.foundry_telemetry_dataset_rid,
        telemetry_view_rid=cfg.foundry_telemetry_view_rid,
        ontology=cfg.foundry_ontology,
        command_object_type=cfg.foundry_command_object_type,
    )
    return FoundryClient(
        token_provider=_build_token_provider(cfg),
        endpoints=endpoints,
        drone_id=cfg.drone_id,
        buffer_path=cfg.telemetry_buffer_path,
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
