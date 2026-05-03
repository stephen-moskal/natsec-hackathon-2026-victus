"""Doctrine-adherence evaluation harness.

Loads an eval set (e.g. shared/protocol/drone_command_adherence_v1_1.json),
drives the model through llama-server, parses the model's plain-text reply
against the doctrine §8 line-based contract (CMD/REPLY/RATIONALE), scores
each test on five axes (format, keyword, parameters, reply, rationale), and
writes a JSONL record + a markdown digest.

Modules:
    parser   line-based output parser
    scorer   per-axis PASS/WARN/FAIL against expectedCommand
    runner   async orchestrator (load → call model → parse → score → record)
"""
