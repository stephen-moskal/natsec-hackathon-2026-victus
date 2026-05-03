# Foundry side

Operator-facing components: ingestion, ontology, orchestration, and the Workshop dashboard.

## Layout

```
foundry/
├── transforms-python/    # PySpark transforms over inbound telemetry
├── functions/            # TypeScript Foundry functions (issueCommand, etc.)
├── ontology/             # Ontology design notes (object/link/action types)
└── workshop/             # Dashboard layout notes and variable definitions
```

These directories hold *source code and design notes* that mirror what we build inside Foundry. Foundry is the source of truth at runtime; this repo is the source of truth for code review and reproducibility.

## Data path

```
Edge POST  ─►  REST API data source (webhook)
                        │
                        ▼
              raw_telemetry  (streaming dataset)
                        │
                        ▼     transforms-python
              telemetry_normalized
                        │
                        ▼
              ontology objects (Drone, Detection, ReasoningTrace, ...)
                        │
                        ▼
              Workshop widgets
```

## Command path

```
Workshop button ─► Foundry function: issueCommand(...)
                        │ writes
                        ▼
              ontology object: Command (status=PENDING)
                        │
                        ▼
              edge polls /commands?drone_id=...&since=...
                        │
                        ▼
              edge POSTs CommandAck → status=ACCEPTED|REJECTED|EXPIRED
```

## Auth (hackathon)

A single bearer token shared across drones. Set in the REST API data source config and injected into edge `config.py` via env. Production would use per-drone mTLS; out of scope.

## What lives where in Foundry

### Live in Foundry (Phases 1, 2, 3 — bidirectional bridge + mission ontology proven against real Foundry)

| Foundry resource | RID / API name |
|---|---|
| Stack | `https://victus.usw-23.palantirfoundry.com` |
| Namespace | `Victus-743ed7` (`ri.compass.main.folder.1b5350a4-4ac5-4803-9c21-1c8096941798`) |
| Project folder | `/Victus-743ed7/phantomORCHESTRATION-hackathon` (`ri.compass.main.folder.e5c96633-8b74-4268-bd42-f4d0d2e3ca53`) |
| Data subfolder | `/Victus-743ed7/phantomORCHESTRATION-hackathon/orchestration-data` (`ri.compass.main.folder.bd1b025f-8c76-4cf4-9964-10c5e35ed537`) |
| Ontology | Victus Ontology (RID `ri.ontology.main.ontology.10d8565f-992c-4cd2-8df5-0328b5d7e46b`); API name `ontology-abe5026d-72be-438c-980f-344a88cff4dc` |
| **Streaming dataset: raw_telemetry** | `ri.foundry.main.dataset.ed8731a7-4d5c-4741-96bb-fcc2f09608cf` — receives every edge envelope via Streams V2 `publishRecords` |
| Backing dataset: drone_state_v3 | `ri.foundry.main.dataset.213600e9-5eff-40d1-89c2-dc0548ba7aca` (3 seed drones, all-STRING/DOUBLE schema) |
| Backing dataset: commands_v3 | `ri.foundry.main.dataset.44e4dd0d-e444-4ace-9121-ba30d26fb64f` (all-STRING schema; live rows from operator UI + curl) |
| **Backing dataset: missions_v1** | `ri.foundry.main.dataset.5c3510f5-decd-4a81-8a3d-7ffe1f80fba9` (all-STRING schema, 13 cols, PK `mission_id`; `system_prompt` is the hero long-text field) |
| Object type: Drone | API `drone` (RID `ri.ontology.main.object-type.0c191bf4-db2f-459c-85c3-1834fa62affa`), PK `drone_id` |
| Object type: Command | API `command` (RID `ri.ontology.main.object-type.9bda313a-b7aa-4c45-8341-85bd627e59ae`), PK `message_id` |
| **Object type: Mission** | API `mission` (id `pzqmccug.mission`, RID `ri.ontology.main.object-type.4689d999-c463-4295-b968-ae1e771581d8`), PK `mission_id`, 13 props, `systemPrompt` long-text |
| Link type: Drone Commands | API `commands`/`drone` (RID `ri.ontology.main.relation.d59d5af5-9d4b-4f0c-bac2-aaac748d1c36`) |
| Action type: Issue Command | API `issue-command` (RID `ri.actions.main.action-type.72c1d608-fbe0-49fb-9e39-bcee55ade3dd`) |
| **Action type: Create Mission** | API `create-mission` (RID `ri.actions.main.action-type.17fefe30-b91f-4d24-a54e-c9f57812701f`) — `addObject` on Mission with all 13 properties as parameters |
| Global branch (merged): Phase 1 | `phantom-orchestration-phase1` (`ri.branch..branch.b9f173a4-9ded-4626-94ad-3d8b3be2e472`); proposal `ri.branch..proposal.125fa621-231d-46da-a009-20cb7746ce2a` DEPLOYED |
| Global branch (merged): Phase 3 | `phantom-orchestration-mission` (`ri.branch..branch.fd2dba29-6829-4ba3-a470-0c280c46de68`); proposal `ri.branch..proposal.9b35de96-3727-4675-9220-8cbd04f71b79` DEPLOYED |

### How the API directions are wired (no HTTPS Listener, no TS v2 function)

| Direction | API | Endpoint shape |
|---|---|---|
| Edge → Foundry (telemetry) | **Streams V2 publishRecords** | `POST {stack}/api/v2/highScale/streams/datasets/{rawTelemetryRid}/streams/master/publishRecords` |
| Foundry → Edge (commands) | **Ontology Search Objects** | `POST {stack}/api/v2/ontologies/{ontology}/objects/command/search` filtered on `deviceId == <drone> AND status == PENDING` |
| Operator (UI/curl) → Foundry (issue command) | **Ontology Action Apply** | `POST {stack}/api/v2/ontologies/{ontology}/actions/issue-command/apply` |
| Operator (UI) → Foundry (create mission) | **Ontology Action Apply** | `POST {stack}/api/v2/ontologies/{ontology}/actions/create-mission/apply` |
| Operator (UI) → Foundry (list missions) | **Ontology Search Objects** | `POST {stack}/api/v2/ontologies/{ontology}/objects/mission/search` |
| BFF → Foundry (assign mission) | Composite | One Search Objects (look up mission) + N Action Apply (`issue-command` with `verb=ASSIGN_MISSION`, `params_json` containing the system prompt) |

Same Foundry bearer token works for all of them. Required scopes: `api:streams-write` + `api:ontologies-read` + `api:ontologies-write`.

The browser never holds the token: it talks to the **BFF** at [`bff/`](../bff/), which proxies to Foundry. See [bff/README.md](../bff/README.md).

### Property API name conventions (Foundry auto-camelCases at deploy time)

The edge code translates between snake_case (wire envelope) and camelCase (Foundry property API names) at the HTTP boundary.

| Object | Property ID (snake_case) | API name (camelCase) |
|---|---|---|
| drone | `drone_id` | `droneId` |
| drone | `lat` / `lon` | `latitude` / `longitude` |
| drone | `alt_m` | `altitudeM` |
| drone | `heading_deg` / `speed_mps` / `battery_pct` | `headingDeg` / `speedMs` / `batteryPercentage` |
| drone | `last_seen_at` / `current_mission_id` / `link_status` / `protocol_version` | `lastSeenAt` / `currentMissionId` / `linkStatus` / `protocolVersion` |
| command | `message_id` / `device_id` / `mission_id` | `messageId` / `deviceId` / `missionId` |
| command | `params_json` | `paramsJson` |
| command | `issued_at` / `expires_at` / `acked_at` / `completed_at` | `issuedAt` / `expiresAt` / `ackedAt` / `completedAt` |
| mission | `mission_id` | `missionId` |
| mission | `system_prompt` / `target_specs` / `area_geo_json` | `systemPrompt` / `targetSpecs` / `areaGeoJson` |
| mission | `roe_profile` / `assigned_device_ids` | `roeProfile` / `assignedDeviceIds` |
| mission | `created_at` / `updated_at` | `createdAt` / `updatedAt` |

### Empty-value convention

Foundry's CSV importer treats `,,` as NULL, which violates `nullable: false` columns. The v3 datasets use the literal string **`"none"`** for any optional/unset field (`current_mission_id`, `mission_id`, `acked_at`, `completed_at`, `supersedes`). The edge and stub both follow this convention.

### Pending (Phase 4+)

| Foundry resource | Phase | Status |
|---|---|---|
| Workshop module `Victus Operator Console` | superseded | Replaced by the standalone React UI in [`ui/`](../ui/) — Workshop module deferred unless we want the dual surface |
| `commands_status` streaming transform: read `CommandAck` events from `raw_telemetry`, flip `command.status` from PENDING → ACKED in `commands_v3`; also handle `MissionEvent` → COMPLETED/ABORTED | 4 | not yet built — UI currently shows all commands as PENDING even after the edge ACKs |
| `drone_state_live` streaming transform: latest `Position` event per `sender` projected into `drone_state_v3` (lat/lon/alt/heading/speed/battery + `last_seen_at`) | 4 | not yet built — `DroneCard` link dots are red because seed `last_seen_at` is hours stale |
| `last_reasoning` object type + transform: latest `ReasoningTrace` event per `sender` | 4 | not yet built — UI's `LLMTracePanel` placeholder waiting on the data source |
| `last_frame` object type + transform: latest `FrameThumbnail` event per `sender` | 4 | not yet built — UI's `VideoPanel` placeholder waiting on the data source |
| Multi-device `issue-command` action variant taking `deviceIds[]` | future | UI fans out N single-device calls today via `Promise.allSettled`; works fine, but a batch action would halve roundtrips |
| `videoFrame` / `textMessage` object types | future | telemetry side; lower priority than the Phase 4 transforms above |

## Subdirectory READMEs

- [transforms-python/README.md](transforms-python/README.md)
- [functions/README.md](functions/README.md)
- [ontology/README.md](ontology/README.md)
- [workshop/README.md](workshop/README.md)
