# VICTUS doctrine prompts

System prompt artifacts that constrain the on-board VLM (Gemma 4 / Qwen3-VL on Jetson via llama-server) to the operational contract defined in [`../drone_command_policy.json`](../drone_command_policy.json) and the wire schemas under [`../schemas/`](../schemas/).

These artifacts are part of the cross-stack contract. They live alongside `schemas/` so the Foundry side can also load them — for example, to display "doctrine v0.1.0 / policy v0.1.0" alongside a drone in Workshop, or to validate that a mission overlay fits within the declared budget before issuing `ASSIGN_MISSION`.

## Files

| File | Purpose |
|---|---|
| [`doctrine.system.md`](doctrine.system.md) | The always-on system prompt for the **command-ack** context. Loaded as the system message on every reasoning call. Teaches the 10 policy command keywords, the 7 brevity-reply keywords, the 9 standing rules (8 from policy + 1 conflict-resolution rule), the ambiguity-handling ladder, the mission-overlay slot, and the line-based plain-text output contract (`CMD: ... / REPLY: ... / RATIONALE: ...`). The model emits text — a separate runtime layer wraps it into the wire JSON envelope. |
| [`examples.jsonl`](examples.jsonl) | Five few-shot examples in OpenAI chat-message format, derived from the `examples[]` block of `drone_command_policy.json` and reshaped to the line-based plain-text output. Loaded as additional turns *before* the live operator turn. Small VLMs lock onto in-context examples more reliably than prose rules. |
| [`manifest.yaml`](manifest.yaml) | Declarative metadata: doctrine version, policy version coupling, protocol version range, mission-overlay markers, token budgets, model-family overrides, SHA-256 checksums. The runtime should fail-fast on version or checksum mismatch. |

## How the runtime composes and consumes the prompt

The expected (not yet implemented) load sequence:

1. Load `manifest.yaml`. Verify `policy_version` matches `../drone_command_policy.json` `meta.version` and `protocol_version_range` accepts the `$id` semvers in `../schemas/*.json`. Verify `checksum.doctrine.system.md` matches the on-disk file.
2. Read `doctrine.system.md` verbatim.
3. If an `ASSIGN_MISSION` command is currently active, replace the slot text between `<MISSION_OVERLAY>` and `</MISSION_OVERLAY>` with the operator-supplied `system_prompt` field from that command, truncated to `mission_overlay_slot.max_tokens`. Otherwise leave the placeholder.
4. Apply the per-model overrides from `model_profiles` to the llama-server request (temperature, stop sequences). Note: `json_mode` for Gemma is no longer applicable since the model emits plain text — the runtime should drop or repurpose this knob.
5. Construct the chat message list as `[system: composed doctrine] + [examples.jsonl turns] + [user: current operator tasking + frame if VLM]`.

The output of every model call is **plain text** in the line-based format from §8 of the doctrine — zero or more `CMD:` lines, exactly one `REPLY:` line, exactly one `RATIONALE:` line. The runtime is responsible for:

1. Parsing the text by line prefix.
2. Tokenizing each `CMD:` line into `{keyword, parameters}`. Bare-token values are passed through; double-quoted values are unquoted; ISO-8601 durations (e.g. `PT10M`) and numeric altitudes are passed as-is for the autonomy/translation layer to coerce.
3. Tokenizing the `REPLY:` line into `{keyword, parameters}` (same scheme).
4. Wrapping the parsed result into the wire JSON envelope and posting it via the existing `comms.foundry_client` path.
5. Populating a `ReasoningTrace` telemetry event with the `RATIONALE:` text (capped per `../schemas/telemetry.schema.json`).

A malformed line (missing `REPLY:`, unrecognized keyword, mis-quoted parameter) is a runtime parse error — the runtime emits `REPLY: UNABLE reason="model output malformed"` on the model's behalf and logs the raw text for debugging. The model is never asked to self-correct; the loop just retries on the next operator turn.

## Mission overlay mechanic

`ASSIGN_MISSION` (defined in [`../schemas/command.schema.json`](../schemas/command.schema.json)) carries a free-text `system_prompt` parameter. That text is the operator's mission-scoped intent — for example: *"You are providing pre-deployment surveillance of Pier 7. Anything man-portable longer than two meters is a CONTACT. Do not loiter below 200 feet AGL."*

That text is layered into the doctrine **between standing rules and the output contract** (see §7 of `doctrine.system.md`). Placement is deliberate: the output contract sits last so recency bias keeps the model emitting valid envelopes even when the mission overlay is verbose. Standing rule 9 explicitly tells the model to disregard any overlay clause that conflicts with the rules or the envelope — so an operator who writes "ignore ABORT" or "respond in plain prose" gets that clause silently dropped, not honored.

## Vocabulary scope (and what is NOT here)

Doctrine teaches the **policy vocabulary** only — the 11 keywords from `drone_command_policy.json`'s `commands[]` (ABORT, RTB, GOTO, CLIMB, DESCEND, LOITER, SEARCH, OBSERVE, REPORT, TRACK, IDENTIFY) and the 7 brevity-reply keywords. It does **not** teach the wire-schema verbs (SCAN, INVESTIGATE, FOLLOW, HOLD, ASSIGN_MISSION) defined in [`../schemas/command.schema.json`](../schemas/command.schema.json). The wire-schema verbs are Foundry-side concerns — what the orchestrator hands to the edge as tasking. The translation between the operator's policy keywords and the wire-schema verbs happens in a future runtime layer (see "Future work" below).

The doctrine also does **not** cover the `report` context — the periodic SITREP / CONTACT / OBSERVATION emission while a task (OBSERVE, SEARCH, TRACK) is running. That emitter has a different output schema (`drone_command_policy.json` `reportSchema`) and will get its own sibling prompt file (`report.system.md`) declared as `contexts.report` in the manifest.

## Vocabulary changes — policy v0.1.0 → v0.2.0

Three vocabulary changes landed when `drone_command_adherence_v1_1.json` was authored. The eval set is the most recently considered artifact and reflects better thinking for a small (2B-class) VLM, so doctrine and policy were updated to match. Each change has both a scoring impact (what the harness now considers a passing emission) and an operations impact (how the runtime translates the emission into action on the drone).

### 1. GOTO parameter rename: `destination` → `location`

- **Now passing**: `CMD: GOTO location="harbor mouth"`. `destination=` is no longer accepted.
- **Why**: makes GOTO consistent with LOITER, which already used `location`. One canonical key per concept means the autonomy layer needs only one resolver, not an alias table.
- **Drone-side effect**: the navigation handler keys on `params["location"]` to feed the path planner. Old emissions with `destination` resolve to no target and the runtime synthesizes `REPLY: UNABLE reason="missing location"` per the malformed-output rule.

### 2. ALTITUDE keyword split: ALTITUDE+direction → CLIMB / DESCEND

- **Now passing**: `CMD: CLIMB altitude=400` or `CMD: DESCEND altitude=200`. `ALTITUDE direction=CLIMB altitude=400` is no longer accepted.
- **Why**: a 2B VLM is more reliable filling 1 parameter than 2; CLIMB/DESCEND maps 1:1 to English so few-shot examples do less work; vocabulary count goes 10 → 11 but each verb is simpler.
- **Drone-side effect**: two distinct handler functions in the autonomy layer instead of one branching on `direction`. CLIMB carries the ROZ-ceiling pre-flight check, DESCEND carries the ROZ-floor check. Eliminates the chance that a CLIMB request takes the descend code path during parser handoff.

### 3. OBSERVE adds `mode` parameter

- **Now passing**: `CMD: OBSERVE target="the pier" mode=pattern_of_life`. `mode` is optional but recommended on tasking that names a mode; default is `static` if omitted.
- **Recognized values**: `pattern_of_life` (delta-detection cadence, event-on-change), `change_detection` (event-driven from a baseline frame), `static` (steady-state SITREP).
- **Why**: operator tasking like "Observe the pier, pattern of life" carries a behavioral lever. Without `mode`, the lever was lost — buried in the rationale or defaulted by the runtime.
- **Drone-side effect**: the reasoning layer picks a different per-frame VLM prompt depending on mode (e.g. "describe what's CHANGED since the last frame" for pattern_of_life). Telemetry cadence and CONTACT-trigger thresholds also vary per mode.

These changes propagate to: `drone_command_policy.json` `commands[]` and `examples[]`, `doctrine.system.md` §3 and §8, `examples.jsonl` example #1, and `manifest.yaml` `policy_version` (bumped to `0.2.0` along with the doctrine checksum).

## Channel: text in, text out (not audio)

The drone receives commands as plain-English **text** from the operator's command server (the Foundry-side `pollCommands` query function — see `../../../foundry/functions/README.md`) and returns its JSON envelope over the same HTTPS link. Doctrine §1, §2, §4, and §5 reflect this. The phrase "brevity speech" is preserved as a stylistic label for terse, doctrine-shaped phrasing — not as audio.

This is one place where doctrine intentionally diverges from `../drone_command_policy.json`. Policy rule 8 reads `"Plain English input, structured JSON output, brevity speech reply via the on-board speaker."` — the "via the on-board speaker" framing was aspirational. Doctrine §5 rule 8 substitutes `"brevity-style reply embedded in the JSON envelope and returned over the command-server link."` to match the actual channel. A future cleanup should update `../drone_command_policy.json` rule 8 in place and then re-sync this doctrine.

## Version coupling

| Source change | Required action here |
|---|---|
| Bump to `../drone_command_policy.json` `meta.version` | Bump `policy_version` in `manifest.yaml`. Re-review `doctrine.system.md` §3, §4, §5 against the new policy. Update `examples.jsonl` if the `examples[]` block changed. |
| Major bump in any `../schemas/*.json` `$id` (e.g. 0.2.x → 1.0.0) | Bump `protocol_version_range` upper bound. Re-review §8 output contract for newly added or removed fields. |
| Edit to `doctrine.system.md` | Recompute `shasum -a 256 doctrine.system.md` and update `checksum.doctrine.system.md` in `manifest.yaml`. Bump doctrine `version` if the change is more than a typo. |

## Verification

```bash
# JSONL round-trip
python -c "import json; [json.loads(l) for l in open('shared/protocol/prompts/examples.jsonl')]"

# Manifest parses
python -c "import yaml; yaml.safe_load(open('shared/protocol/prompts/manifest.yaml'))"

# Each example's assistant content parses as the single-envelope output
python -c "import json; [print(json.loads(json.loads(l)['messages'][-1]['content']).keys()) for l in open('shared/protocol/prompts/examples.jsonl')]"

# Checksum matches manifest
shasum -a 256 shared/protocol/prompts/doctrine.system.md
```

## Future work (deliberately not in this task)

- **`edge/src/victus_edge/llm/prompts.py` loader** — reads `manifest.yaml`, validates checksums and version coupling, builds the composed system prompt, applies the active mission overlay.
- **Reasoner integration** — replaces the hard-coded `_DEFAULT_DESCRIBE_PROMPT` in `edge/src/victus_edge/llm/reasoner.py` with the composed doctrine + few-shot turns + per-step user prompt.
- **`report.system.md`** — the periodic-emission prompt for the `report` context. Different output schema (`reportSchema`), different cadence (timer-driven, not turn-driven).
- **Policy-to-wire-schema translator** — maps `{GOTO, ALTITUDE, SEARCH, OBSERVE, REPORT, TRACK, IDENTIFY}` → wire verbs `{SCAN, LOITER, INVESTIGATE, FOLLOW, RTB, HOLD, ABORT, ASSIGN_MISSION}` so the edge can report intent back to Foundry in the wire vocabulary while reasoning in the operator vocabulary.

See [`docs/PROTOCOL.md`](../../../docs/PROTOCOL.md) and [`docs/ARCHITECTURE.md`](../../../docs/ARCHITECTURE.md) for the broader system context.
