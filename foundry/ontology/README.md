# Ontology design

The ontology is small by design. Every object type has a clear backing dataset and a clear consumer in Workshop.

## Object types

### `drone`
Primary key: `drone_id`. One row per known drone.

| Property | Type | Source |
|---|---|---|
| `drone_id` | string (PK) | edge `sender` field |
| `callsign` | string | static config |
| `last_seen_at` | timestamp | latest `Position` event |
| `lat`, `lon`, `alt_m` | double | latest `Position` |
| `heading_deg`, `speed_mps` | double | latest `Position` |
| `battery_pct` | double | latest `Position` |
| `state` | string | latest `Status.state` |
| `current_command_id` | string | latest accepted `Command` |
| `link_status` | string | derived: `ONLINE` if heartbeat within 10 s else `LINK_LOST` |

### `command`
Primary key: `message_id`. Lifecycle: `PENDING → ACCEPTED → COMPLETED|ABORTED|EXPIRED|REJECTED`.

| Property | Type | Source |
|---|---|---|
| `message_id` | string (PK) | function `issueCommand` |
| `drone_id` | string (FK → drone) | function input |
| `verb` | string | function input |
| `params_json` | string | function input |
| `priority` | string | function input |
| `issued_at`, `expires_at` | timestamp | function input |
| `status` | string | derived from `CommandAck` and `MissionEvent` |
| `supersedes` | string | function input |

### `detection`
Primary key: `detection_id`. One per vision detection emitted by the edge.

| Property | Type | Source |
|---|---|---|
| `detection_id` | string (PK) | edge |
| `drone_id` | string (FK → drone) | envelope `sender` |
| `observed_at` | timestamp | envelope `issued_at` |
| `class` | string | edge |
| `confidence` | double | edge |
| `lat`, `lon` | double | edge (if georeferenced) |
| `bbox_json` | string | edge |
| `frame_ref` | string | optional thumbnail RID |

### `reasoning-trace`
Primary key: `message_id`. One per LLM reasoning step.

| Property | Type | Source |
|---|---|---|
| `message_id` | string (PK) | edge |
| `drone_id` | string (FK → drone) | envelope `sender` |
| `command_id` | string (FK → command) | edge |
| `decision` | string | edge |
| `rationale` | string | edge (truncated to ~500 chars) |
| `tokens` | int | edge |
| `at` | timestamp | envelope `issued_at` |

### `mission` (optional, Phase 3+)
Groups commands into a higher-level operator intent. Primary key: `mission_id`. One operator session = one mission.

## Link types

| Link | From → To | Cardinality |
|---|---|---|
| `drone-commands` | `drone` → `command` | ONE_TO_MANY |
| `command-traces` | `command` → `reasoning-trace` | ONE_TO_MANY |
| `drone-detections` | `drone` → `detection` | ONE_TO_MANY |
| `mission-commands` | `mission` → `command` | ONE_TO_MANY |

## Action types

| Action | Function | Notes |
|---|---|---|
| `Issue Command` | `issueCommand` | Primary operator action. |
| `Cancel Command` | `cancelCommand` | Available on any `PENDING` or `ACCEPTED` command. |
| `Set ROE` | `setROE` | Drone-scoped. |

## Ontology hygiene

- Use a Foundry **branch** for ontology changes during the hackathon. Merge to main only when Phase 1 is green.
- Every object type's backing dataset must have a unique non-null primary key. Validate in the corresponding transform.
- Geometry properties (`lat`/`lon` columns) — if we wire a map widget, also expose a derived `geo_point` property of `GeoPoint` type per the Maritime project convention.
