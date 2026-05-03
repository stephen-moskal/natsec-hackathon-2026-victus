# Protocol — Command & Telemetry Dictionary

This is the shared vocabulary spoken between Foundry and edge. It is intentionally small. Anything not in this dictionary is rejected at the schema layer.

**Source of truth for the verb set:** [drone_command_policy.json](../drone_command_policy.json) at the repo root — defines the plain-English vocabulary the on-board LLM responds to. The schemas below mirror that policy.

Schemas: [shared/protocol/schemas/](../shared/protocol/schemas/)

## Design rules

- **JSON only**, UTF-8, one envelope per message.
- **Versioned.** Every message carries `protocol_version` (semver). Edge and Foundry refuse messages with mismatched majors.
- **Idempotent.** Every message has a UUID `message_id`. Receivers dedupe.
- **Time-bounded.** Every command carries an `expires_at` (ISO 8601 UTC). After expiry, the edge falls back to its safe behavior (`ABORT`-equivalent: hold safely + cancel intent).
- **Self-contained.** A receiver should never need to look up prior state to interpret a message.

## Envelope

```json
{
  "protocol_version": "0.3.0",
  "message_id": "uuid-v4",
  "issued_at": "2026-05-02T18:00:00Z",
  "sender": "foundry-orchestrator | drone-<id>",
  "kind": "command | telemetry",
  "payload": { ... }
}
```

## Command vocabulary (Foundry → edge)

A command's `payload` always has a `verb` and verb-specific `params`. Verbs are ordered by **policy priority** (1 = highest precedence on the wire).

### Verbs

| Pri | Verb | Required params | Optional params | Meaning |
|---|---|---|---|---|
| 1 | `ABORT` | — | — | Halt current task immediately, return to safe holding state. Never blocked. |
| 2 | `RTB` | — | — | Return to base / launch point. |
| 3 | `GOTO` | `destination` (string: lat/lon, MGRS, or named landmark) | `altitude` (ft AGL) | Fly to specified location. |
| 4 | `ALTITUDE` | `direction` (`CLIMB` \| `DESCEND`), `altitude` (ft AGL) | — | Change altitude. |
| 5 | `LOITER` | `duration` (ISO 8601, e.g. `PT10M`) | `location` (defaults to current) | Hold position for the given duration. |
| 6 | `SEARCH` | `area` (string), `target` (string, plain-English) | `pattern` (defaults to "parallel sweep") | Sweep area for target. |
| 7 | `OBSERVE` | `target` (string) | `duration` (default `PT30M`), `reportInterval` (default `PT60S`) | Pattern-of-life watch. |
| 8 | `REPORT` | — | `subject` (default "current scene"), `interval` (one-shot if absent) | SITREP on demand or periodically. |
| 9 | `TRACK` | `target` (string) | `standOffMeters` | Follow a moving target. |
| 10 | `IDENTIFY` | `target` (string) | — | Classify a specific object (type, size, count, activity). |
| — | `ASSIGN_MISSION` | `mission_id`, `name`, `system_prompt` | `priority`, `roe_profile` | Operator action — delivers an LLM system-prompt fragment. |

### Modifiers

Every command also carries:

| Field | Type | Required | Notes |
|---|---|---|---|
| `drone_id` | string | yes | Receiving drone. |
| `priority` | enum | yes | `ROUTINE` \| `PRIORITY` \| `IMMEDIATE` \| `FLASH`. Higher preempts lower. |
| `expires_at` | ISO 8601 UTC | yes | After this, drone falls back to safe behavior. |
| `roe` | string | no | ROE profile id; unknown profile → `ABORT`. |
| `supersedes` | UUID | no | `message_id` of a command this replaces. |

### Example — SEARCH

```json
{
  "protocol_version": "0.3.0",
  "message_id": "f4c1...",
  "issued_at": "2026-05-02T18:00:00Z",
  "sender": "foundry-orchestrator",
  "kind": "command",
  "payload": {
    "drone_id": "uav-01",
    "verb": "SEARCH",
    "priority": "PRIORITY",
    "expires_at": "2026-05-02T18:30:00Z",
    "params": {
      "area": "the harbor",
      "target": "small boats",
      "pattern": "parallel sweep"
    }
  }
}
```

## Telemetry vocabulary (edge → orchestrator)

Telemetry events are tagged by `event` type within `payload`.

### Infrastructure events

| Event | Required fields | Meaning |
|---|---|---|
| `Position` | `lat`, `lon`, `alt_m`, optional `heading_deg`/`speed_mps`/`battery_pct` | Periodic state heartbeat. |
| `Status` | `state` (enum), optional `flags[]` | Health: `NOMINAL` \| `DEGRADED` \| `BINGO` \| `WINCHESTER` \| `LINK_LOST`. |
| `FrameThumbnail` | `format` (jpeg), `width`, `height`, `b64` | Compressed frame sample (≤600 KB). |
| `Detection` | `detection_id`, `class`, `confidence`, `bbox`, optional `geo`, `frame_ref` | Vision detection. |
| `ReasoningTrace` | `command_id`, `decision`, `rationale` (≤500 chars) | One LLM reasoning step. |

### Command lifecycle (drone brevity replies, per policy)

| Event | Result enum | Meaning |
|---|---|---|
| `CommandAck` | `WILCO` | Acknowledged and will comply (replaces old `ACCEPTED` in 0.3.0). |
| `CommandAck` | `UNABLE` | Cannot comply; `reason` field required. |
| `CommandAck` | `ROGER` | Received and understood (no compliance commitment — used for `REPORT`). |
| `CommandAck` | `STANDBY` | Processing or temporarily unavailable. |
| `CommandAck` | `EXPIRED` | System-level — picked up after `expires_at`. |
| `MissionEvent` | `event_kind` ∈ {`STARTED`, `COMPLETED`, `ABORTED`, `FALLBACK_HOLD`} | Lifecycle marker. |

### Reports (per policy reportSchema)

| Event | Required fields | Trigger |
|---|---|---|
| `Sitrep` | `observed_at`, `location` ({lat, lon, mgrs?}), `scene`, `link_state` ∈ {CONNECTED, DENIED, RECOVERING} | `REPORT` verb cadence or one-shot. |
| `Contact` | + `command_id`, `contacts[]` ({description, confidence}) | `SEARCH`/`TRACK`/`IDENTIFY` matches above confidence threshold. |
| `Observation` | + `command_id`, `delta` (what changed) | `OBSERVE` delta detection. |

### Resource alerts

| Event | Fields | Meaning |
|---|---|---|
| `Bingo` | `resource` (string, e.g. "fuel"), optional `remaining_pct` | Monitored resource at minimum threshold. |
| `Nodeloss` | — | Self-reported imminent loss of the node. |

### Status state machine (edge-reported)

```
NOMINAL ──┬── DEGRADED ──┬── BINGO ──── RTB ──── (landed)
          │              │
          └── LINK_LOST  └── WINCHESTER  (sensors/payload exhausted)
```

`LINK_LOST` is reported retroactively in the buffered batch once the link returns; until then it is implicit.

### Operator-visible command status (derived)

The orchestrator-side transform projects `CommandAck` and `MissionEvent` into a 5-state machine on the `command` ontology object:

```
PENDING ──► ACKED ──► COMPLETED
   │           │
   │           └────► ABORTED        (MissionEvent: ABORTED | FALLBACK_HOLD)
   ├──► EXPIRED                       (CommandAck: EXPIRED, or now > expires_at AND PENDING)
   └──► REJECTED                      (CommandAck: UNABLE)
```

`WILCO`, `ROGER`, and `STANDBY` all map to `ACKED`. `UNABLE` maps to `REJECTED`.

## Error handling

- **Schema-invalid messages** are dropped at the receiver and logged. Sender is not informed (no error channel in MVP).
- **Unknown verbs** → `CommandAck { result: UNABLE, reason: "command unclear, say again" }` per policy rule.
- **Conflicting commands** → newer command with `supersedes` wins; otherwise priority wins; ties go to most recent.
- **Expired commands** at the edge → `CommandAck { result: EXPIRED }`, drone falls back to `ABORT` semantics (hold safely).
- **`linkState=DENIED`** → drone queues all reports locally; flushes on recovery in `observed_at` order (per policy rule).

## Versioning policy

- `0.x.y` during the hackathon. Anything goes. Both sides redeploy together.
- `1.0.0` will lock the verb set. Adding a verb is a minor bump. Changing required params is a major bump.

### Changelog

- **0.3.0** — aligned to [drone_command_policy.json](../drone_command_policy.json):
  - **Verb dictionary replaced**: removed `HOLD`, `SCAN`, `INVESTIGATE`, `FOLLOW`; added `GOTO`, `ALTITUDE`, `OBSERVE`, `REPORT`, `IDENTIFY`; renamed `SCAN→SEARCH`, `FOLLOW→TRACK`. `ASSIGN_MISSION` retained for operator missions.
  - `LOITER` params changed: `center/radius_m/altitude_m` → `duration` (ISO 8601), optional `location`.
  - **`CommandAck.result` changed** from `ACCEPTED|REJECTED|EXPIRED` to **`WILCO|UNABLE|ROGER|STANDBY|EXPIRED`** (drone brevity terms).
  - **New telemetry events**: `Sitrep`, `Contact`, `Observation` (per policy reportSchema), `Bingo`, `Nodeloss`.
  - Both edge and Foundry must be redeployed together.
- **0.2.0** — added `ASSIGN_MISSION` verb so operator missions (LLM system-prompt fragments) ride the existing command channel instead of requiring a separate fetch.
- **0.1.0** — initial protocol.
