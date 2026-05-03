"""Line-based output parser for the doctrine §8 contract.

The doctrine instructs the model to emit:

    CMD: <KEYWORD> key1=value1 key2="value with spaces"
    CMD: <KEYWORD> ...
    REPLY: <RESPONSE_KEYWORD> reason="..."
    RATIONALE: <one sentence>

Zero or more CMD lines, exactly one REPLY, exactly one RATIONALE.

This parser is forgiving on shape (it tolerates extra blank lines, leading
whitespace, mixed-case keywords) but precise on structure — every issue is
recorded in `ParsedReply.issues` with a severity (WARN or FAIL) so the
scorer can use them. The runtime command-side parser uses the same module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .vocabulary import COMMAND_KEYWORDS, REPLY_KEYWORDS


_LINE_RE = re.compile(r"^(?P<prefix>CMD|REPLY|RATIONALE)\s*:\s*(?P<rest>.*)$")

# parameter token: key=bareword | key="quoted value" | key='quoted value'
_PARAM_RE = re.compile(
    r"""
    (?P<key>[A-Za-z_][A-Za-z0-9_]*)
    \s*=\s*
    (?:
        "(?P<dq>(?:[^"\\]|\\.)*)"     # double-quoted
      | '(?P<sq>(?:[^'\\]|\\.)*)'     # single-quoted
      | (?P<bare>[^\s"']+)            # bare token (no spaces, no quotes)
    )
    """,
    re.VERBOSE,
)


@dataclass
class ParsedCommand:
    keyword: str
    params: dict[str, Any]


@dataclass
class ParsedReply:
    """One reply keyword with its parameters (e.g. UNABLE reason='...')."""

    keyword: str
    params: dict[str, Any]


@dataclass
class ParseIssue:
    severity: str        # "WARN" | "FAIL"
    code: str            # short machine-readable code
    message: str         # human-readable detail


@dataclass
class ParsedOutput:
    commands: list[ParsedCommand] = field(default_factory=list)
    reply: ParsedReply | None = None
    rationale: str | None = None
    issues: list[ParseIssue] = field(default_factory=list)
    raw: str = ""

    @property
    def has_fail(self) -> bool:
        return any(i.severity == "FAIL" for i in self.issues)

    @property
    def has_warn(self) -> bool:
        return any(i.severity == "WARN" for i in self.issues)


def parse(raw: str) -> ParsedOutput:
    """Parse one model output string into commands / reply / rationale."""
    out = ParsedOutput(raw=raw)

    text = (raw or "").strip()
    if not text:
        out.issues.append(ParseIssue("FAIL", "empty_output", "Model returned no text."))
        return out

    # Reject obvious off-contract shapes early. JSON is the most likely failure
    # mode given the doctrine flipped from JSON-out to text-out recently.
    if text.startswith("{") or text.startswith("["):
        out.issues.append(
            ParseIssue("FAIL", "json_output", "Model emitted JSON; doctrine §8 requires line-based plain text.")
        )
    if "```" in text:
        out.issues.append(
            ParseIssue("WARN", "markdown_fence", "Model output contains ``` fences — doctrine §8 forbids them.")
        )

    reply_seen = False
    rationale_seen = False
    extras: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        m = _LINE_RE.match(line)
        if not m:
            extras.append(line)
            continue
        prefix = m.group("prefix").upper()
        rest = m.group("rest").strip()

        if prefix == "CMD":
            cmd = _parse_cmd_line(rest, out)
            if cmd is not None:
                out.commands.append(cmd)
        elif prefix == "REPLY":
            if reply_seen:
                out.issues.append(
                    ParseIssue("WARN", "duplicate_reply", "Multiple REPLY lines; using the first.")
                )
                continue
            reply_seen = True
            out.reply = _parse_reply_line(rest, out)
        elif prefix == "RATIONALE":
            if rationale_seen:
                out.issues.append(
                    ParseIssue("WARN", "duplicate_rationale", "Multiple RATIONALE lines; using the first.")
                )
                continue
            rationale_seen = True
            out.rationale = rest

    if extras:
        out.issues.append(
            ParseIssue(
                "WARN",
                "extra_content",
                f"{len(extras)} non-prefixed line(s) ignored: {extras[0][:80]!r}{'...' if len(extras) > 1 else ''}",
            )
        )

    if not reply_seen:
        out.issues.append(ParseIssue("FAIL", "missing_reply", "No REPLY: line in output."))
    if not rationale_seen:
        out.issues.append(ParseIssue("FAIL", "missing_rationale", "No RATIONALE: line in output."))

    return out


def _parse_cmd_line(rest: str, out: ParsedOutput) -> ParsedCommand | None:
    parts = rest.split(maxsplit=1)
    if not parts:
        out.issues.append(ParseIssue("FAIL", "empty_cmd", "CMD: line had no keyword."))
        return None

    keyword = parts[0].upper()
    if keyword not in COMMAND_KEYWORDS:
        out.issues.append(
            ParseIssue("FAIL", "unknown_cmd_keyword", f"CMD keyword {keyword!r} is not in the doctrine vocabulary.")
        )
        # still record it so the scorer can compare against expected keyword

    params_str = parts[1] if len(parts) > 1 else ""
    params = _parse_params(params_str, out, context=f"CMD {keyword}")
    return ParsedCommand(keyword=keyword, params=params)


def _parse_reply_line(rest: str, out: ParsedOutput) -> ParsedReply | None:
    parts = rest.split(maxsplit=1)
    if not parts:
        out.issues.append(ParseIssue("FAIL", "empty_reply", "REPLY: line had no keyword."))
        return None

    keyword = parts[0].upper()
    if keyword not in REPLY_KEYWORDS:
        out.issues.append(
            ParseIssue("FAIL", "unknown_reply_keyword", f"REPLY keyword {keyword!r} is not in the doctrine vocabulary.")
        )

    params_str = parts[1] if len(parts) > 1 else ""
    params = _parse_params(params_str, out, context=f"REPLY {keyword}")
    return ParsedReply(keyword=keyword, params=params)


def _parse_params(params_str: str, out: ParsedOutput, context: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if not params_str:
        return params

    pos = 0
    matched_any = False
    for m in _PARAM_RE.finditer(params_str):
        matched_any = True
        # detect skipped non-whitespace between matches
        gap = params_str[pos:m.start()].strip()
        if gap:
            out.issues.append(
                ParseIssue("WARN", "stray_token", f"{context}: stray token between params: {gap!r}")
            )
        key = m.group("key")
        value = m.group("dq") if m.group("dq") is not None else (
            m.group("sq") if m.group("sq") is not None else m.group("bare")
        )
        # try numeric coercion for bare tokens
        if m.group("bare") is not None:
            value = _coerce_bare(value)
        params[key] = value
        pos = m.end()

    trailing = params_str[pos:].strip()
    if trailing:
        out.issues.append(
            ParseIssue("WARN", "trailing_token", f"{context}: trailing unparsed text: {trailing!r}")
        )
    if not matched_any and params_str.strip():
        out.issues.append(
            ParseIssue("WARN", "params_unparsed", f"{context}: param block did not match any key=value pair: {params_str!r}")
        )

    return params


def _coerce_bare(token: str) -> Any:
    """Bare tokens that look like numbers become numbers; ISO-8601 durations and
    enum-ish identifiers stay as strings."""
    try:
        if "." in token:
            return float(token)
        return int(token)
    except ValueError:
        return token
