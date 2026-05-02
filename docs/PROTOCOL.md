# Protocol — Command & Telemetry Dictionary

This is the shared vocabulary spoken between Foundry and edge. It is intentionally small. Anything not in this dictionary is rejected at the schema layer.

Schemas: [shared/protocol/schemas/](../shared/protocol/schemas/)

## Design rules

- **JSON only**, UTF-8, one envelope per message.
- **Versioned.** Every message carries `protocol_version` (semver). Edge and Foundry refuse messages with mismatched majors.
- **Idempotent.** Every message has a UUID `message_id`. Receivers dedupe.
- **Time-bounded.** Every command carries an `expires_at` (ISO 8601 UTC). After expiry, the edge falls back to its safe behavior (`HOLD` by default).
- **Self-contained.** A receiver should never need to look up prior state to interpret a message.

## Envelope

```json
{
  "protocol_version": "0.1.0",
  "message_id": "uuid-v4",
  "issued_at": "2026-05-02T18:00:00Z",
  "sender": "foundry-orchestrator | drone-<id>",
  "kind": "command | telemetry",
  "payload": { ... }
}
```

## Command vocabulary (Foundry → edge)

A command's `payload` always has a `verb` and verb-specific `params`.

### Verbs (MVP set)

| Verb | Meaning | Required params |
|---|---|---|
| `SCAN` | Sweep an area, report detections. | `area` (geojson polygon), `pattern` (`grid` \| `spiral`), `altitude_m` |
| `LOITER` | Hold position or orbit a point. | `center` (geojson point), `radius_m`, `altitude_m` |
| `INVESTIGATE` | Move to a target, observe, report. | `target` (geojson point or `detection_id`), `dwell_s` |
| `FOLLOW` | Track a moving contact. | `contact_id`, `standoff_m`, `altitude_m` |
| `RTB` | Return to base. | `base` (geojson point) optional; defaults to launch point |
| `HOLD` | Stop and hover safely. | none |
| `ABORT` | Cancel current intent and execute safe fallback. | `reason` (string) |
| `ASSIGN_MISSION` | Update the LLM system-prompt fragment for this drone (delivers a mission). | `mission_id` (string), `name` (string), `system_prompt` (string), optional `priority`, `roe_profile` |

### Modifiers (apply to any verb)

| Field | Meaning |
|---|---|
| `priority` | `ROUTINE` \| `PRIORITY` \| `IMMEDIATE` \| `FLASH`. Higher priorities preempt lower. |
| `roe` | Rules of engagement profile id (string). Edge enforces what it knows; unknown profile → `ABORT`. |
| `expires_at` | ISO 8601 UTC. After this, the command is no longer valid. |
| `supersedes` | Optional `message_id` of a command this one replaces. |

### Example: SCAN

```json
{
  "protocol_version": "0.1.0",
  "message_id": "f4c1...",
  "issued_at": "2026-05-02T18:00:00Z",
  "sender": "foundry-orchestrator",
  "kind": "command",
  "payload": {
    "drone_id": "uav-01",
    "verb": "SCAN",
    "priority": "PRIORITY",
    "expires_at": "2026-05-02T18:30:00Z",
    "params": {
      "area": { "type": "Polygon", "coordinates": [[[ ... ]]] },
      "pattern": "grid",
      "altitude_m": 80
    }
  }
}
```

## Telemetry vocabulary (edge → Foundry)

Telemetry events are tagged by `event` type within `payload`.

| Event | Meaning | Notable fields |
|---|---|---|
| `Position` | Periodic state. | `lat`, `lon`, `alt_m`, `heading_deg`, `speed_mps`, `battery_pct` |
| `Status` | Health summary. | `state` (`NOMINAL` \| `DEGRADED` \| `BINGO` \| `WINCHESTER` \| `LINK_LOST`), `flags[]` |
| `Detection` | Vision detection. | `detection_id`, `class`, `confidence`, `bbox`, `geo` (lat/lon if georeferenced), `frame_ref` |
| `ReasoningTrace` | LLM reasoning step. | `command_id`, `decision`, `rationale` (short), `tokens` |
| `FrameThumbnail` | Compressed sample frame. | `format` (`jpeg`), `width`, `height`, `b64` |
| `CommandAck` | Acknowledges a received command. | `command_id`, `result` (`ACCEPTED` \| `REJECTED` \| `EXPIRED`), `reason` |
| `MissionEvent` | Lifecycle marker. | `event_kind` (`STARTED` \| `COMPLETED` \| `ABORTED` \| `FALLBACK_HOLD`), `command_id` |

### Status state machine (edge-reported)

```
NOMINAL ──┬── DEGRADED ──┬── BINGO ──── RTB ──── (landed)
          │              │
          └── LINK_LOST  └── WINCHESTER  (sensors/payload exhausted)
```

`LINK_LOST` is reported retroactively in the buffered batch once the link returns; until then it is implicit.

## Error handling

- **Schema-invalid messages** are dropped at the receiver and logged. Sender is not informed (no error channel in MVP).
- **Unknown verbs** → `CommandAck { result: REJECTED, reason: "unknown_verb" }`.
- **Conflicting commands** → newer command with `supersedes` wins; otherwise priority wins; ties go to most recent.
- **Expired commands** at the edge → `CommandAck { result: EXPIRED }`, drone falls back to `HOLD`.

## Versioning policy

- `0.x.y` during the hackathon. Anything goes.
- `1.0.0` locks the verb set. Adding a verb is a minor bump. Changing required params is a major bump.

### Changelog

- **0.2.0** — added `ASSIGN_MISSION` verb so operator missions (LLM system-prompt fragments) ride the existing command channel instead of requiring a separate fetch. Schemas in `shared/protocol/schemas/` updated; both edge and Foundry must be redeployed.
- **0.1.0** — initial protocol.
