"""Per-axis adherence scoring against an expected command from the eval set.

Five axes:
  - format     parse cleanliness (CMD/REPLY/RATIONALE structure)
  - keyword    commands[0].keyword == expected.keyword
  - parameters every expected param key/value is present in the parsed command
  - reply      a REPLY: line is present, keyword is valid, required params present
  - rationale  RATIONALE present and within the budget (≤ 80 words / 500 chars,
               or ≤ 30 words / 200 chars when the expected keyword is IDENTIFY)

Each axis returns a `Verdict` of PASS | WARN | FAIL plus a short note.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .parser import ParsedOutput
from .vocabulary import REPLY_KEYWORDS, required_reply_params


PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass
class AxisVerdict:
    verdict: str           # "PASS" | "WARN" | "FAIL"
    note: str | None       # short explanation; None when uneventful


@dataclass
class TestScore:
    format: AxisVerdict
    keyword: AxisVerdict
    parameters: AxisVerdict
    reply: AxisVerdict
    rationale: AxisVerdict

    @property
    def overall(self) -> str:
        verdicts = [self.format.verdict, self.keyword.verdict, self.parameters.verdict,
                    self.reply.verdict, self.rationale.verdict]
        if FAIL in verdicts:
            return FAIL
        if WARN in verdicts:
            return WARN
        return PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": asdict(self.format),
            "keyword": asdict(self.keyword),
            "parameters": asdict(self.parameters),
            "reply": asdict(self.reply),
            "rationale": asdict(self.rationale),
            "verdict": self.overall,
        }


def score(parsed: ParsedOutput, expected: dict[str, Any]) -> TestScore:
    """Compare a parsed output against an `expectedCommand` block from the eval set.

    `expected` is the eval set's `expectedCommand` field: `{keyword, parameters}`.
    """
    expected_keyword = (expected.get("keyword") or "").upper()
    expected_params = expected.get("parameters") or {}

    return TestScore(
        format=_score_format(parsed),
        keyword=_score_keyword(parsed, expected_keyword),
        parameters=_score_parameters(parsed, expected_params),
        reply=_score_reply(parsed),
        rationale=_score_rationale(parsed, expected_keyword),
    )


# --- per-axis scorers --------------------------------------------------------

def _score_format(parsed: ParsedOutput) -> AxisVerdict:
    fail_codes = {i.code for i in parsed.issues if i.severity == FAIL}
    warn_codes = {i.code for i in parsed.issues if i.severity == WARN}

    # Format-fatal issues
    fatal = {"empty_output", "json_output", "missing_reply", "missing_rationale",
             "empty_cmd", "empty_reply"}
    if fail_codes & fatal:
        msg = ", ".join(sorted(fail_codes & fatal))
        return AxisVerdict(FAIL, msg)

    # Other FAILs (e.g. unknown keyword) are not format issues — they belong
    # to keyword/reply axes. Format is purely structural.
    structural_warns = {"markdown_fence", "extra_content", "duplicate_reply",
                        "duplicate_rationale", "trailing_token", "stray_token",
                        "params_unparsed"}
    if warn_codes & structural_warns:
        msg = ", ".join(sorted(warn_codes & structural_warns))
        return AxisVerdict(WARN, msg)

    return AxisVerdict(PASS, None)


def _score_keyword(parsed: ParsedOutput, expected_keyword: str) -> AxisVerdict:
    if not parsed.commands:
        return AxisVerdict(FAIL, "no CMD line emitted")
    actual = parsed.commands[0].keyword.upper()
    if actual == expected_keyword:
        return AxisVerdict(PASS, None)
    return AxisVerdict(FAIL, f"expected {expected_keyword}, got {actual}")


def _score_parameters(parsed: ParsedOutput, expected_params: dict[str, Any]) -> AxisVerdict:
    if not parsed.commands:
        return AxisVerdict(FAIL, "no CMD line — cannot compare parameters")
    actual_params = parsed.commands[0].params

    missing: list[str] = []
    mismatched: list[str] = []
    for key, exp_val in expected_params.items():
        if key not in actual_params:
            missing.append(key)
            continue
        if not _values_equivalent(actual_params[key], exp_val):
            mismatched.append(f"{key}: expected={exp_val!r} actual={actual_params[key]!r}")

    if missing or mismatched:
        notes = []
        if missing:
            notes.append("missing=" + ",".join(missing))
        if mismatched:
            notes.append("mismatch=" + "; ".join(mismatched))
        return AxisVerdict(FAIL, "; ".join(notes))

    extras = set(actual_params) - set(expected_params)
    if extras:
        return AxisVerdict(WARN, "extra params: " + ",".join(sorted(extras)))

    return AxisVerdict(PASS, None)


def _score_reply(parsed: ParsedOutput) -> AxisVerdict:
    if parsed.reply is None:
        return AxisVerdict(FAIL, "no REPLY line")
    kw = parsed.reply.keyword.upper()
    if kw not in REPLY_KEYWORDS:
        return AxisVerdict(FAIL, f"reply keyword {kw!r} not in vocabulary")

    required = required_reply_params(kw)
    missing = required - set(parsed.reply.params)
    if missing:
        return AxisVerdict(FAIL, f"REPLY {kw} missing required params: {','.join(sorted(missing))}")

    return AxisVerdict(PASS, None)


def _score_rationale(parsed: ParsedOutput, expected_keyword: str) -> AxisVerdict:
    if not parsed.rationale:
        return AxisVerdict(FAIL, "no RATIONALE line")
    text = parsed.rationale.strip()
    chars = len(text)
    words = len(text.split())

    is_identify = expected_keyword == "IDENTIFY"
    char_cap = 200 if is_identify else 500
    word_cap = 30 if is_identify else 80
    note = f"{words} words, {chars} chars"

    if chars > char_cap or words > word_cap:
        return AxisVerdict(FAIL, f"over budget: {note} (cap {word_cap}w / {char_cap}c)")

    if words < 5:
        return AxisVerdict(WARN, f"thin: {note}")

    # near-budget warn (within 10% of cap)
    if chars > 0.9 * char_cap or words > 0.9 * word_cap:
        return AxisVerdict(WARN, f"near cap: {note}")

    return AxisVerdict(PASS, note)


def _values_equivalent(actual: Any, expected: Any) -> bool:
    """Loose equality: numeric tolerance, case-insensitive string compare,
    string-vs-number coercion (the parser may produce ints where the eval
    set has strings or vice versa)."""
    if actual == expected:
        return True
    # numeric tolerance
    try:
        if abs(float(actual) - float(expected)) < 1e-6:
            return True
    except (TypeError, ValueError):
        pass
    # case-insensitive string compare (after stringifying both sides)
    return str(actual).strip().lower() == str(expected).strip().lower()
