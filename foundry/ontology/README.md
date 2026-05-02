# Ontology design — Phase 1

Five object types live in the new product folder (RID `ri.compass.main.folder.e5c96633-8b74-4268-bd42-f4d0d2e3ca53`). Every type has a clear backing dataset and a clear consumer in Workshop.

## Object types

### `drone`
Latest-row-per-device projection. Backing: streaming dataset `drone_state`, primary key `drone_id`.

| Property | Type | Source |
|---|---|---|
| `drone_id` | string (PK) | edge envelope `sender` (stripped of `drone-` prefix) |
| `callsign` | string | static config / `Status` event |
| `protocol_version` | string | envelope `protocol_version` |
| `last_seen_at` | timestamp | latest event of any kind |
| `position` | GeoPoint (`lat,lon`) | latest `Position` event |
| `alt_m` | double | latest `Position` |
| `heading_deg`, `speed_mps`, `battery_pct` | double | latest `Position` |
| `state` | string | latest `Status.state` (`NOMINAL`/`DEGRADED`/`BINGO`/`WINCHESTER`/`LINK_LOST`) |
| `current_mission_id` | string (FK → mission) | derived from latest accepted `ASSIGN_MISSION` command |
| `link_status` | string | derived: `ONLINE` if `last_seen_at` within 10 s else `LINK_LOST` |

### `command`
Streaming projection from issued commands joined with `CommandAck` and `MissionEvent` events. Backing: `commands_log`, primary key `message_id`.

| Property | Type | Source |
|---|---|---|
| `message_id` | string (PK) | function `issueCommand` |
| `device_id` | string (FK → drone) | function input |
| `mission_id` | string (FK → mission, nullable) | function input |
| `verb` | string | function input |
| `params_json` | string | function input (raw JSON; schema validates inner shape elsewhere) |
| `priority` | string | function input |
| `status` | string | derived from `CommandAck` and `MissionEvent` (see lifecycle below) |
| `issued_at` | timestamp | function input |
| `expires_at` | timestamp | function input |
| `acked_at` | timestamp (nullable) | first `CommandAck` event |
| `completed_at` | timestamp (nullable) | first `MissionEvent` with `event_kind=COMPLETED` |
| `supersedes` | string (nullable) | function input |

#### Status lifecycle

```
PENDING ──► ACKED ──► COMPLETED
   │           │
   │           └────► ABORTED        (MissionEvent: ABORTED | FALLBACK_HOLD)
   ├──► EXPIRED                       (CommandAck: EXPIRED, or derived: now > expires_at AND PENDING)
   └──► REJECTED                      (CommandAck: REJECTED)
```

`ACKED` is the "operator can see it was received" state — the chip color in Workshop is bound directly to this enum. The query function never writes back; lifecycle moves entirely on telemetry events the edge emits.

### `videoFrame`
Latest frame per drone, **updated in place** (one row per device, not appended). Backing: streaming `frame_metadata`, primary key `drone_id`.

| Property | Type | Source |
|---|---|---|
| `drone_id` | string (PK, FK → drone) | envelope `sender` |
| `frame_id` | string | edge per-frame UUID |
| `captured_at` | timestamp | envelope `issued_at` |
| `position` | GeoPoint | telemetry `FrameThumbnail.geo` (or last known `Position`) |
| `altitude_m` | double | as above |
| `heading_deg` | double | as above |
| `width`, `height` | int | telemetry `FrameThumbnail` |
| `format` | string | telemetry `FrameThumbnail.format` (`jpeg`) |
| `image_b64` | string | telemetry `FrameThumbnail.b64` (capped at ~600 KB by edge) |
| `detections_json` | string | edge — JSON array of recent detections for this frame |

Workshop renders `image_b64` directly via the image widget. Historical replay is out of scope for Phase 1; if needed in Phase 2, split into a separate `frame_history` append-only dataset + media files.

### `textMessage`
Bidirectional operator/edge messaging. Backing: batch dataset `text_messages`, primary key `message_id`. Phase 1 supports operator → edge only; edge → operator requires adding a `TextMessage` event to `telemetry.schema.json` (Phase 2).

| Property | Type | Source |
|---|---|---|
| `message_id` | string (PK) | UUID at write time |
| `direction` | string enum | `OPERATOR_TO_EDGE` \| `EDGE_TO_OPERATOR` |
| `sender_id` | string | function input or envelope `sender` |
| `recipient_id` | string (FK → drone) | function input |
| `body` | string | function input (max 12 MB; expect <2 KB) |
| `session_id` | string (nullable) | function input — groups a conversation thread |
| `in_reply_to_message_id` | string (nullable) | function input — enables threading |
| `ack_status` | string | `PENDING` \| `ACKED` (set by edge ack telemetry, Phase 2) |
| `sent_at` | timestamp | function input |
| `acked_at` | timestamp (nullable) | edge ack |

### `mission`
Operator-defined intent. The `system_prompt` is the LLM prompt fragment delivered to the edge via `ASSIGN_MISSION`. Backing: batch dataset `missions`, primary key `mission_id`.

| Property | Type | Source |
|---|---|---|
| `mission_id` | string (PK) | function `assignMission` |
| `name` | string | function input |
| `description` | string (nullable) | function input |
| `system_prompt` | string | function input — the LLM prompt fragment |
| `prompt_version` | int | starts at 1; bump on edit (reserved — versioning UI is Phase 2) |
| `prompt_updated_at` | timestamp | latest edit |
| `priority` | string | function input |
| `roe_profile` | string (nullable) | function input |
| `active` | boolean | toggled by `startMission` / `stopMission` |
| `created_at` | timestamp | function input |
| `started_at`, `ended_at` | timestamp (nullable) | start/stop actions |

Assignment to devices is via the `mission-devices` link type, **not** an array property.

## Link types

| Link | From → To | Cardinality | Backing |
|---|---|---|---|
| `drone-commands` | `drone` → `command` | ONE_TO_MANY | derived from `command.device_id` |
| `drone-frames` | `drone` → `videoFrame` | ONE_TO_ONE | derived from `videoFrame.drone_id` (latest-frame model) |
| `drone-messages-sent` | `drone` → `textMessage` | ONE_TO_MANY | filter `textMessage.sender_id = drone_id` |
| `drone-messages-received` | `drone` → `textMessage` | ONE_TO_MANY | filter `textMessage.recipient_id = drone_id` |
| `mission-commands` | `mission` → `command` | ONE_TO_MANY | derived from `command.mission_id` |
| `mission-devices` | `mission` ↔ `drone` | MANY_TO_MANY | join dataset written by `assignMission` action |

## Action types (function-backed, TS v2)

| Action | Function | Effect |
|---|---|---|
| Issue Command | `issueCommand(deviceIds[], verb, params, priority, expiresAt, missionId?, supersedes?)` | Validates against `command.schema.json`; writes one Command row per device with status `PENDING`. |
| Cancel Command | `cancelCommand(commandId, reason)` | Sets target command to `REJECTED` and emits a superseding `ABORT` to the same drone. |
| Send Text Message | `sendTextMessage(recipientDeviceIds[], body, sessionId?)` | Writes one TextMessage row per recipient with `direction=OPERATOR_TO_EDGE, ack_status=PENDING`. |
| Assign Mission | `assignMission(missionId, deviceIds[])` | Writes the `mission-devices` link rows; emits `ASSIGN_MISSION` Command to each device carrying `{mission_id, name, system_prompt}`. |
| Start Mission | `startMission(missionId)` | Sets `mission.active=true`, `started_at=now`. |
| Stop Mission | `stopMission(missionId)` | Sets `mission.active=false`, `ended_at=now`. |

All operator actions are configured for multi-device fan-out via array inputs. Internally each function loops with `createEditBatch()` so the writes are atomic per call.

## Ontology hygiene

- Use a Foundry **branch** for ontology changes during the hackathon. Merge to main only when Phase 1.0 round-trip is green.
- Every object type's backing dataset must have a unique non-null primary key. Validate in the corresponding transform.
- Geometry properties — use `GeoPoint` (not `string`) so Workshop map widgets render. Document exact format (`lat,lon`, no parens) in the transform that produces them.
