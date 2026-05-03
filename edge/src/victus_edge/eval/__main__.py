"""CLI entry point for the doctrine-adherence eval harness.

Usage:
    python -m victus_edge.eval                        # legacy doctrine prompt
    python -m victus_edge.eval --gbnf                 # GBNF-constrained slim prompt
    python -m victus_edge.eval --gbnf --eval-set <p>  # custom eval set
    python -m victus_edge.eval --gbnf --llm-url http://localhost:8080

The harness loads the eval set, drives each `operatorInput` through llama-server
with the doctrine system prompt + few-shot examples, and writes a JSONL +
markdown worksheet to the output directory.

`--gbnf` swaps the 1742-token doctrine.system.md for the slim
doctrine_gbnf.system.md and applies doctrine.gbnf to constrain the sampler.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import structlog

from ..llm.http_client import LlamaCppClient
from .runner import _REPO_ROOT, run_eval_set


log = structlog.get_logger(__name__)


_DEFAULT_EVAL_SET = _REPO_ROOT / "shared" / "protocol" / "drone_command_adherence_v1_1.json"
_DEFAULT_OUTPUT_DIR = Path.cwd() / "eval_runs"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="victus_edge.eval",
        description="Run the doctrine-adherence eval harness against a running llama-server.",
    )
    p.add_argument(
        "--gbnf",
        action="store_true",
        help="Use the slim system prompt + GBNF grammar (doctrine_gbnf.system.md + doctrine.gbnf).",
    )
    p.add_argument(
        "--eval-set",
        type=Path,
        default=_DEFAULT_EVAL_SET,
        help=f"Path to eval set JSON (default: {_DEFAULT_EVAL_SET}).",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help=f"Output directory for JSONL + markdown (default: {_DEFAULT_OUTPUT_DIR}).",
    )
    p.add_argument(
        "--model-name",
        type=str,
        default="unknown",
        help='Logical model name recorded in the JSONL row (e.g. "qwen3-vl-2b").',
    )
    p.add_argument(
        "--llm-url",
        type=str,
        default="http://localhost:8080",
        help="Base URL for the running llama-server (default: http://localhost:8080).",
    )
    p.add_argument("--max-tokens", type=int, default=512)
    p.add_argument("--temperature", type=float, default=0.1)
    p.add_argument(
        "--stop",
        action="append",
        default=None,
        help="Stop sequence; repeat for multiple. Default: none on the wire.",
    )
    p.add_argument(
        "--timeout-s",
        type=float,
        default=120.0,
        help="HTTP timeout per chat-completion call (default: 120s).",
    )
    return p.parse_args(argv)


async def _run(args: argparse.Namespace) -> None:
    log.info(
        "eval_starting",
        gbnf=args.gbnf,
        eval_set=str(args.eval_set),
        output=str(args.output),
        llm_url=args.llm_url,
        model_name=args.model_name,
    )
    async with LlamaCppClient(args.llm_url, timeout_s=args.timeout_s) as client:
        if not await client.health():
            raise RuntimeError(
                f"llama-server at {args.llm_url} is not healthy — start it first "
                "(or pass --llm-url to point at the right host:port)."
            )
        jsonl_path, md_path = await run_eval_set(
            client,
            args.eval_set,
            args.output,
            model_name=args.model_name,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            stop=args.stop,
            use_grammar=args.gbnf,
        )
    log.info("eval_done", jsonl=str(jsonl_path), markdown=str(md_path))


def main() -> None:
    asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    main()
