"""CLI parsing, model-path resolution, and Config-in-test-mode coverage."""

import pytest

from victus_edge.config import _parse_gst_index, _parse_webcam_index, load
from victus_edge.main import _build_overrides, _MODEL_TABLE, _parse_args, _resolve_model_paths
from victus_edge.runtime.factory import build_foundry_client, build_vision
from victus_edge.vision.pipeline import GstSource, WebcamSource


# ---------- argparse ----------

def test_parse_test_flag():
    args = _parse_args(["--test"])
    assert args.test is True
    assert args.webcam is None
    assert args.model is None


def test_parse_webcam_with_index():
    args = _parse_args(["--webcam", "2"])
    assert args.webcam == 2


def test_parse_webcam_default_zero():
    args = _parse_args(["--webcam"])
    assert args.webcam == 0


def test_parse_gst_webcam_with_index():
    args = _parse_args(["--gst-webcam", "1"])
    assert args.gst_webcam == 1
    assert args.webcam is None


def test_parse_gst_webcam_default_zero():
    args = _parse_args(["--gst-webcam"])
    assert args.gst_webcam == 0


def test_webcam_and_gst_webcam_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        _parse_args(["--webcam", "0", "--gst-webcam", "0"])


def test_parse_model_choices():
    args = _parse_args(["--model", "gemma4"])
    assert args.model == "gemma4"

    args = _parse_args(["--model", "qwen-vl"])
    assert args.model == "qwen-vl"


def test_parse_explicit_paths():
    args = _parse_args(["--model-path", "/x.gguf", "--mmproj-path", "/y.gguf"])
    assert args.model_path == "/x.gguf"
    assert args.mmproj_path == "/y.gguf"


# ---------- model path resolution ----------

def test_resolve_explicit_paths_win():
    args = _parse_args(["--model", "gemma4", "--model-path", "/x.gguf"])
    model, mmproj = _resolve_model_paths(args)
    assert model == "/x.gguf"
    # mmproj falls back to gemma4 table since no --mmproj-path given
    assert mmproj == _MODEL_TABLE["gemma4"][1]


def test_resolve_model_table():
    args = _parse_args(["--model", "qwen-vl"])
    model, mmproj = _resolve_model_paths(args)
    assert model == _MODEL_TABLE["qwen-vl"][0]
    assert mmproj == _MODEL_TABLE["qwen-vl"][1]


def test_resolve_no_args_no_paths():
    args = _parse_args([])
    model, mmproj = _resolve_model_paths(args)
    assert model is None
    assert mmproj is None


# ---------- overrides ----------

def test_overrides_test_mode_implies_webcam_zero():
    args = _parse_args(["--test"])
    o = _build_overrides(args)
    assert o["test_mode"] is True
    assert o["vision_source"] == "webcam:0"
    assert o["llm_backend"] == "llama_cpp_server"


def test_overrides_test_mode_with_explicit_webcam():
    args = _parse_args(["--test", "--webcam", "3"])
    o = _build_overrides(args)
    assert o["vision_source"] == "webcam:3"


def test_overrides_gst_webcam_routes_to_gst_source_string():
    args = _parse_args(["--test", "--gst-webcam", "0"])
    o = _build_overrides(args)
    assert o["vision_source"] == "gst:0"
    assert o["llm_backend"] == "llama_cpp_server"


def test_overrides_gst_webcam_without_test():
    args = _parse_args(["--gst-webcam", "2"])
    o = _build_overrides(args)
    assert o["vision_source"] == "gst:2"


def test_overrides_no_llama_server_flag():
    args = _parse_args(["--test", "--no-llama-server"])
    o = _build_overrides(args)
    assert o["manage_llama_server"] is False


def test_overrides_fps():
    args = _parse_args(["--test", "--fps", "0.5"])
    o = _build_overrides(args)
    assert o["vision_fps"] == 0.5


# ---------- Config in test mode ----------

def test_load_test_mode_skips_token_validation(monkeypatch):
    """In test mode, FOUNDRY_TOKEN is not required and Foundry URLs may be empty."""
    # Strip any inherited Foundry env so the validation would otherwise fail
    for var in ("FOUNDRY_TOKEN", "FOUNDRY_LISTENER_URL", "FOUNDRY_FUNCTIONS_URL", "VICTUS_DRONE_ID"):
        monkeypatch.delenv(var, raising=False)

    cfg = load(overrides={"test_mode": True})
    assert cfg.test_mode is True
    assert cfg.foundry_token is None
    assert cfg.foundry_listener_url == ""
    assert cfg.drone_id == "test-drone"


def test_load_production_mode_still_requires_token(monkeypatch):
    monkeypatch.delenv("FOUNDRY_TOKEN", raising=False)
    monkeypatch.setenv("VICTUS_DRONE_ID", "x")
    monkeypatch.setenv("FOUNDRY_LISTENER_URL", "http://l")
    monkeypatch.setenv("FOUNDRY_FUNCTIONS_URL", "http://f")

    with pytest.raises(RuntimeError, match="FOUNDRY_TOKEN"):
        load()


def test_load_overrides_win_over_env(monkeypatch):
    monkeypatch.setenv("VICTUS_VISION_SOURCE", "mock")
    cfg = load(overrides={"test_mode": True, "vision_source": "webcam:5"})
    assert cfg.vision_source == "webcam:5"
    assert cfg.webcam_device_index == 5


# ---------- vision_source parsing ----------

def test_parse_webcam_index_basic():
    assert _parse_webcam_index("webcam:0") == 0
    assert _parse_webcam_index("webcam:7") == 7


def test_parse_webcam_index_non_webcam():
    assert _parse_webcam_index("mock") is None
    assert _parse_webcam_index("file:/path.mp4") is None
    assert _parse_webcam_index("gst:v4l2src ...") is None


def test_parse_webcam_index_malformed():
    assert _parse_webcam_index("webcam:") is None
    assert _parse_webcam_index("webcam:abc") is None


def test_parse_gst_index_basic():
    assert _parse_gst_index("gst:0") == 0
    assert _parse_gst_index("gst:3") == 3


def test_parse_gst_index_non_gst():
    assert _parse_gst_index("webcam:0") is None
    assert _parse_gst_index("mock") is None
    assert _parse_gst_index("file:/x.mp4") is None


def test_parse_gst_index_malformed():
    assert _parse_gst_index("gst:") is None
    assert _parse_gst_index("gst:xyz") is None


# ---------- factory dispatch ----------

def test_build_foundry_client_returns_none_in_test_mode(monkeypatch):
    for var in ("FOUNDRY_TOKEN", "FOUNDRY_LISTENER_URL", "FOUNDRY_FUNCTIONS_URL", "VICTUS_DRONE_ID"):
        monkeypatch.delenv(var, raising=False)
    cfg = load(overrides={"test_mode": True})
    assert build_foundry_client(cfg) is None


def test_build_vision_returns_webcam_source(monkeypatch):
    for var in ("FOUNDRY_TOKEN", "FOUNDRY_LISTENER_URL", "FOUNDRY_FUNCTIONS_URL", "VICTUS_DRONE_ID"):
        monkeypatch.delenv(var, raising=False)
    cfg = load(overrides={"test_mode": True, "vision_source": "webcam:0"})
    src = build_vision(cfg)
    assert isinstance(src, WebcamSource)
    assert src._device_index == 0


def test_build_vision_returns_gst_source(monkeypatch):
    for var in ("FOUNDRY_TOKEN", "FOUNDRY_LISTENER_URL", "FOUNDRY_FUNCTIONS_URL", "VICTUS_DRONE_ID"):
        monkeypatch.delenv(var, raising=False)
    cfg = load(overrides={"test_mode": True, "vision_source": "gst:0"})
    src = build_vision(cfg)
    assert isinstance(src, GstSource)
    assert src._device_index == 0


def test_build_vision_returns_none_for_mock_source(monkeypatch):
    for var in ("FOUNDRY_TOKEN", "FOUNDRY_LISTENER_URL", "FOUNDRY_FUNCTIONS_URL", "VICTUS_DRONE_ID"):
        monkeypatch.delenv(var, raising=False)
    cfg = load(overrides={"test_mode": True, "vision_source": "mock"})
    assert build_vision(cfg) is None
