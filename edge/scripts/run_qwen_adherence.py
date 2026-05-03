#!/usr/bin/env python3
"""CLI entrypoint: boot llama-server with Qwen3-VL, run the adherence eval.

Usage (on Jetson, from repo root):

    python -m edge.scripts.run_qwen_adherence \
        --eval-set shared/protocol/drone_command_adherence_v1_1.json \
        --output-dir edge/runtime/

Or, if `victus_edge` is installed (pip install -e edge):

    python edge/scripts/run_qwen_adherence.py \
        --eval-set shared/protocol/drone_command_adherence_v1_1.json \
        --output-dir edge/runtime/

Behavior:
  - Spawns llama-server as a child process (via LlamaServer) loading the
    Qwen3-VL 2B Instruct GGUF + mmproj from the paths the existing main.py
    _MODEL_TABLE knows about. Override with --model-path / --mmproj-path.
  - Polls /health, sends each test's operatorInput, captures raw output.
  - Writes JSONL + markdown worksheet under --output-dir.
  - Tears down llama-server cleanly on exit.

Pass --no-llama-server to run against a llama-server already started by
hand (useful for iterating on the doctrine without paying boot cost each
run).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import structlog

# Make repo-root imports work whether the script is run as a module or directly.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "edge" / "src"))

from victus_edge.eval.runner import run_eval_set  # noqa: E402
from victus_edge.llm.http_client import LlamaCppClient  # noqa: E402
from victus_edge.llm.server import LlamaServer  # noqa: E402
from victus_edge.main import _MODEL_TABLE  # noqa: E402


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


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="run_qwen_adherence", description=__doc__)
    p.add_argument(
        "--eval-set",
        type=Path,
        default=_REPO_ROOT / "shared" / "protocol" / "drone_command_adherence_v1_1.json",
        help="Path to the eval set JSON. Default: drone_command_adherence_v1_1.json.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=_REPO_ROOT / "edge" / "runtime",
        help="Directory for JSONL + markdown outputs. Default: edge/runtime/",
    )
    p.add_argument(
        "--model",
        choices=sorted(_MODEL_TABLE.keys()),
        default="qwen-vl",
        help="Model selector for the _MODEL_TABLE (default: qwen-vl).",
    )
    p.add_argument("--model-path", type=Path, help="Override GGUF path.")
    p.add_argument("--mmproj-path", type=Path, help="Override mmproj path.")
    p.add_argument(
        "--no-llama-server",
        action="store_true",
        help="Don't spawn llama-server — connect to one already running.",
    )
    p.add_argument(
        "--llm-server-url",
        default="http://127.0.0.1:8080",
        help="Base URL for llama-server (default http://127.0.0.1:8080).",
    )
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--temperature", type=float, default=0.1)
    p.add_argument(
        "--stop",
        nargs="*",
        default=["\n\n", "```"],
        help='Stop sequences (default: "\\n\\n" "```")',
    )
    p.add_argument("--log-level", default="INFO")
    return p.parse_args()


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    table_model, table_mmproj = _MODEL_TABLE[args.model]
    model = args.model_path if args.model_path else Path(table_model)
    mmproj = args.mmproj_path if args.mmproj_path else Path(table_mmproj)
    return model, mmproj


async def _drive(args: argparse.Namespace) -> int:
    if not args.eval_set.is_file():
        log.error("eval_set_not_found", path=str(args.eval_set))
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.no_llama_server:
        async with LlamaCppClient(args.llm_server_url, timeout_s=120.0) as client:
            jsonl, md = await run_eval_set(
                client,
                eval_set_path=args.eval_set,
                output_dir=args.output_dir,
                model_name=args.model,
                max_tokens=args.max_tokens,
                temperature=args.temperature,
                stop=args.stop or None,
            )
    else:
        model_path, mmproj_path = _resolve_paths(args)
        if not Path(model_path).is_file():
            log.error("model_path_not_found", path=str(model_path))
            return 2
        async with LlamaServer(str(model_path), str(mmproj_path)) as server:
            async with LlamaCppClient(server.base_url, timeout_s=120.0) as client:
                jsonl, md = await run_eval_set(
                    client,
                    eval_set_path=args.eval_set,
                    output_dir=args.output_dir,
                    model_name=args.model,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                    stop=args.stop or None,
                )

    print(f"\nJSONL archive : {jsonl}")
    print(f"Markdown digest: {md}\n")
    return 0


def main() -> int:
    args = _parse_args()
    _configure_logging(args.log_level)
    log.info(
        "qwen_adherence_starting",
        eval_set=str(args.eval_set),
        output_dir=str(args.output_dir),
        model=args.model,
        manage_llama_server=not args.no_llama_server,
    )
    try:
        return asyncio.run(_drive(args))
    except KeyboardInterrupt:
        log.info("interrupted")
        return 130


if __name__ == "__main__":
    sys.exit(main())
