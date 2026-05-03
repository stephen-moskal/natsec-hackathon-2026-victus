"""On-board reasoning model.

Wraps a small VLM (Gemma 4 E4B-it or Qwen3-VL-2B-Instruct) running locally via
llama-server. Backend is selected by config; the `mock` backend returns
deterministic outputs for development without a model.

Two paths through `step()`:

  * ``frame_jpeg`` is provided → multimodal describe via ``describe_frame``
    (Phase 2 vision-driven reasoning).
  * ``frame_jpeg`` is None → text-only reasoning over the operator command.
    Used for command-driven LLM responses on drones without an active video
    feed (e.g. BRAVO at hackathon demo time). The prompt is built from the
    command's verb + params + nl_context.
"""

from dataclasses import dataclass
import json
import re

from .http_client import LlamaCppClient


@dataclass
class ReasoningInput:
    intent: dict           # current command payload (verb, params, priority, …)
    detections: list[dict] # recent vision detections
    frame_jpeg: bytes | None


@dataclass
class ReasoningOutput:
    action: dict           # autonomy-controller action
    decision: str          # short label, e.g. "approach_target"
    rationale: str         # short natural-language explanation, <= 500 chars
    tokens: int


_DEFAULT_DESCRIBE_PROMPT = "Describe what you see in this image briefly."


# System prompt for the text-only command path. Keeps the model focused on the
# tactical-recon role and forces a structured DECISION/RATIONALE output we can
# parse cheaply.
_COMMAND_SYSTEM_PROMPT = (
    "You are an autonomous UAV's on-board tactical reasoner. The operator has "
    "just issued a command. In one sentence each, decide WHAT you will do and "
    "explain WHY based on the command's verb, parameters, and the operator's "
    "natural-language context if present.\n\n"
    "Respond in EXACTLY this format, nothing else:\n"
    "DECISION: <one short imperative line, ~10 words>\n"
    "RATIONALE: <one or two short sentences, <= 400 chars total>"
)


def _build_command_prompt(intent: dict) -> str:
    verb = intent.get("verb", "(unknown)")
    priority = intent.get("priority", "ROUTINE")
    params = intent.get("params") or {}
    # nl_context is the operator's plain-English intent (Phase 3 addition).
    nl_context = params.get("nl_context") if isinstance(params, dict) else None
    structured_params = {k: v for k, v in (params or {}).items() if k != "nl_context"}

    parts = [
        f"Command verb: {verb}",
        f"Priority: {priority}",
        f"Structured parameters: {json.dumps(structured_params, separators=(',', ':'))}",
    ]
    if nl_context:
        parts.append(f"Operator context: {nl_context}")
    return "\n".join(parts)


_DECISION_RE = re.compile(r"DECISION:\s*(.+?)(?:\n|$)", re.IGNORECASE)
_RATIONALE_RE = re.compile(r"RATIONALE:\s*(.+)", re.IGNORECASE | re.DOTALL)


def _parse_decision_rationale(text: str) -> tuple[str, str]:
    """Extract DECISION + RATIONALE lines. Falls back to first/rest split."""
    text = text.strip()
    decision_m = _DECISION_RE.search(text)
    rationale_m = _RATIONALE_RE.search(text)

    if decision_m and rationale_m:
        return decision_m.group(1).strip()[:120], rationale_m.group(1).strip()[:500]

    # Fallback: first line is decision, rest is rationale.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "(no decision)", "(empty model response)"
    decision = lines[0][:120]
    rationale = (" ".join(lines[1:]) or text)[:500]
    return decision, rationale


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
            verb = (inputs.intent or {}).get("verb", "noop")
            return ReasoningOutput(
                action={"do": "noop"},
                decision=f"mock-{verb.lower()}",
                rationale=f"mock backend received verb={verb}",
                tokens=0,
            )
        if self.backend == "llama_cpp_server":
            assert self.client is not None
            if inputs.frame_jpeg is not None:
                # Multimodal path (Phase 2 vision-driven reasoning).
                text = await self.client.describe_frame(
                    inputs.frame_jpeg, prompt=_DEFAULT_DESCRIBE_PROMPT
                )
                return ReasoningOutput(
                    action={"do": "noop"},
                    decision="describe",
                    rationale=text[:500],
                    tokens=0,
                )
            # Text-only command-reasoning path.
            user_prompt = _build_command_prompt(inputs.intent)
            messages = [
                {"role": "system", "content": _COMMAND_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            text = await self.client.chat_completion(
                messages, max_tokens=200, temperature=0.2
            )
            decision, rationale = _parse_decision_rationale(text)
            return ReasoningOutput(
                action={"do": "noop"},
                decision=decision,
                rationale=rationale,
                tokens=len(text.split()),
            )
        raise NotImplementedError(f"unknown reasoner backend: {self.backend}")
