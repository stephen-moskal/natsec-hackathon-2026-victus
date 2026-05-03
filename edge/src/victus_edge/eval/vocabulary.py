"""Canonical command and reply keyword sets, loaded from the policy at import time.

The policy file (`shared/protocol/drone_command_policy.json`) is the source of
truth. We read it once on import so the parser and scorer stay in sync with
the policy automatically — no second copy of the keyword list to drift.

Reply keywords come from `responses[]`. Command keywords come from
`commands[]`. Both are upper-cased.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


# Walk up from this file to the repo root, then into shared/protocol/.
# edge/src/victus_edge/eval/vocabulary.py → repo root is parents[4].
_REPO_ROOT = Path(__file__).resolve().parents[4]
_POLICY_PATH = _REPO_ROOT / "shared" / "protocol" / "drone_command_policy.json"


@lru_cache(maxsize=1)
def _load_policy() -> dict:
    with open(_POLICY_PATH) as fh:
        return json.load(fh)


def policy_version() -> str:
    return _load_policy()["meta"]["version"]


def _command_keywords() -> frozenset[str]:
    return frozenset(c["keyword"].upper() for c in _load_policy()["commands"])


def _reply_keywords() -> frozenset[str]:
    return frozenset(r["keyword"].upper() for r in _load_policy()["responses"])


def required_command_params(keyword: str) -> set[str]:
    """Return the set of required parameter names for a given command keyword.
    Empty set if the command has no required params or the keyword is unknown."""
    for cmd in _load_policy()["commands"]:
        if cmd["keyword"].upper() == keyword.upper():
            return {p["name"] for p in cmd.get("parameters", []) if p.get("required")}
    return set()


def required_reply_params(keyword: str) -> set[str]:
    """Return the set of required parameter names for a given reply keyword."""
    for rep in _load_policy()["responses"]:
        if rep["keyword"].upper() == keyword.upper():
            return {p["name"] for p in rep.get("parameters", []) if p.get("required")}
    return set()


# Materialize on import so parser/scorer can do `if kw in COMMAND_KEYWORDS`.
COMMAND_KEYWORDS: frozenset[str] = _command_keywords()
REPLY_KEYWORDS: frozenset[str] = _reply_keywords()
