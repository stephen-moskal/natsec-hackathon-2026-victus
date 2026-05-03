"""Adherence runner — send mock operator commands, record raw model output.

v1 scope: no automated scoring. The runner sends each `operatorInput` from
the eval set (e.g. `shared/protocol/drone_command_adherence_v1_1.json`)
through llama-server with the doctrine system prompt + few-shot examples
loaded, captures the raw assistant text verbatim, and writes two artifacts:

  1. A JSONL archive (one row per test, full raw output) — for re-grading.
  2. A human-gradable markdown worksheet — operator input, expected command
     for reference, the raw model output in a fenced block, latency, and a
     grading slot the operator fills in by hand.

The runner does NOT use the parser or scorer modules in v1. Those are on
disk for a future automated-scoring pass once we know what good looks like
empirically.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from ..llm.http_client import LlamaCppClient
from .vocabulary import policy_version


log = structlog.get_logger(__name__)


# Repo-root resolution: edge/src/victus_edge/eval/runner.py → parents[4]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_PROMPTS_DIR = _REPO_ROOT / "shared" / "protocol" / "prompts"
_GRAMMARS_DIR = _REPO_ROOT / "shared" / "protocol" / "grammars"
_DOCTRINE_PATH = _PROMPTS_DIR / "doctrine.system.md"
_DOCTRINE_GBNF_PATH = _PROMPTS_DIR / "doctrine_gbnf.system.md"
_GRAMMAR_PATH = _GRAMMARS_DIR / "doctrine.gbnf"
_EXAMPLES_PATH = _PROMPTS_DIR / "examples.jsonl"


@dataclass
class TestRecord:
    test_id: int
    operator_input: str
    expected_command: dict[str, Any]
    raw_output: str
    latency_ms: int
    error: str | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_doctrine(*, gbnf: bool = False) -> str:
    """Return the system-prompt text. `gbnf=True` selects the slim variant
    paired with `doctrine.gbnf`; `False` returns the legacy full prompt.
    """
    return (_DOCTRINE_GBNF_PATH if gbnf else _DOCTRINE_PATH).read_text()


def _read_grammar() -> str:
    """GBNF grammar source for the command-ack context."""
    return _GRAMMAR_PATH.read_text()


def _read_few_shot_messages() -> list[dict[str, Any]]:
    """Flatten examples.jsonl into a single message list (user/assistant pairs)."""
    messages: list[dict[str, Any]] = []
    for line in _EXAMPLES_PATH.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        for msg in obj["messages"]:
            messages.append(msg)
    return messages


def _build_messages(operator_input: str, *, gbnf: bool = False) -> list[dict[str, Any]]:
    """system prompt + few-shot turns + the live user turn."""
    return [
        {"role": "system", "content": _read_doctrine(gbnf=gbnf)},
        *_read_few_shot_messages(),
        {"role": "user", "content": operator_input},
    ]


async def _run_one_test(
    client: LlamaCppClient,
    test: dict[str, Any],
    *,
    max_tokens: int,
    temperature: float,
    stop: list[str] | None,
    use_grammar: bool = False,
) -> TestRecord:
    operator_input = test["operatorInput"]
    expected = test.get("expectedCommand", {})
    messages = _build_messages(operator_input, gbnf=use_grammar)
    grammar = _read_grammar() if use_grammar else None

    log.info(
        "test_dispatch",
        test_id=test["id"],
        operator_input=operator_input,
        gbnf=use_grammar,
    )

    started = time.monotonic()
    try:
        raw = await client.chat_completion(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
            grammar=grammar,
        )
        error: str | None = None
    except Exception as exc:
        raw = ""
        error = f"{type(exc).__name__}: {exc}"
        log.error("test_failed", test_id=test["id"], error=error)
    latency_ms = int((time.monotonic() - started) * 1000)

    return TestRecord(
        test_id=test["id"],
        operator_input=operator_input,
        expected_command=expected,
        raw_output=raw,
        latency_ms=latency_ms,
        error=error,
    )


async def run_eval_set(
    client: LlamaCppClient,
    eval_set_path: Path,
    output_dir: Path,
    *,
    model_name: str,
    max_tokens: int = 512,
    temperature: float = 0.1,
    stop: list[str] | None = None,
    use_grammar: bool = False,
) -> tuple[Path, Path]:
    """Drive every test in the eval set; write JSONL + markdown.

    `use_grammar=True` swaps the legacy doctrine.system.md for the slim
    doctrine_gbnf.system.md and constrains the sampler with doctrine.gbnf.
    `False` preserves legacy behavior.

    Returns (jsonl_path, md_path).
    """
    eval_set = json.loads(eval_set_path.read_text())
    tests = eval_set["tests"]
    eval_name = eval_set.get("evalSet", eval_set_path.stem)

    timestamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_gbnf" if use_grammar else ""
    jsonl_path = output_dir / f"qwen_adherence_{timestamp}{suffix}.jsonl"
    md_path = output_dir / f"qwen_adherence_{timestamp}{suffix}.md"

    records: list[TestRecord] = []
    for test in tests:
        rec = await _run_one_test(
            client, test,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
            use_grammar=use_grammar,
        )
        records.append(rec)
        # Write each row immediately so a crash mid-run doesn't lose data.
        with jsonl_path.open("a") as fh:
            fh.write(json.dumps(_record_to_row(rec, model_name, eval_name, timestamp)) + "\n")
        log.info(
            "test_recorded",
            test_id=rec.test_id,
            latency_ms=rec.latency_ms,
            chars=len(rec.raw_output),
        )

    md_path.write_text(_render_markdown(records, eval_name, model_name, timestamp))
    log.info("eval_run_complete", jsonl=str(jsonl_path), markdown=str(md_path), tests=len(records))
    return jsonl_path, md_path


def _record_to_row(
    rec: TestRecord, model_name: str, eval_name: str, timestamp: str,
) -> dict[str, Any]:
    return {
        "test_id": rec.test_id,
        "timestamp": timestamp,
        "model": model_name,
        "policy_version": policy_version(),
        "eval_set": eval_name,
        "operator_input": rec.operator_input,
        "expected_command": rec.expected_command,
        "raw_output": rec.raw_output,
        "latency_ms": rec.latency_ms,
        "error": rec.error,
    }


# --- markdown worksheet ------------------------------------------------------

def _render_markdown(
    records: list[TestRecord], eval_name: str, model_name: str, timestamp: str,
) -> str:
    header = f"""# Qwen adherence run — {timestamp}

| Field | Value |
|---|---|
| Model | `{model_name}` |
| Policy version | `{policy_version()}` |
| Eval set | `{eval_name}` |
| Tests | {len(records)} |
| Generated at | `{timestamp}` (UTC) |

This worksheet shows what the model emitted for each mock operator command. Compare against the **Expected command** block, then mark **Grade** by hand. The full raw output (including any whitespace, trailing tokens, JSON drift, etc.) is in the fenced block. The companion JSONL has identical data for re-grading.

---
"""

    sections: list[str] = []
    for rec in records:
        expected = rec.expected_command or {}
        expected_kw = expected.get("keyword", "(none)")
        expected_params = expected.get("parameters", {})
        params_block = (
            "\n".join(f"  - `{k}`: `{v!r}`" for k, v in expected_params.items())
            if expected_params else "  *(none)*"
        )
        if rec.error:
            output_block = f"```\n[ERROR] {rec.error}\n```"
        elif not rec.raw_output.strip():
            output_block = "```\n(empty)\n```"
        else:
            output_block = f"```\n{rec.raw_output.rstrip()}\n```"

        sections.append(f"""## Test {rec.test_id} — expected `{expected_kw}`

**Operator input:**

> {rec.operator_input}

**Expected command:**
- keyword: `{expected_kw}`
- parameters:
{params_block}

**Model output:**

{output_block}

**Latency:** {rec.latency_ms} ms

**Grade:**  ☐ PASS  ☐ FAIL  ☐ PARTIAL  &nbsp;&nbsp;&nbsp; **Notes:** ____________________

---
""")

    return header + "\n".join(sections)
