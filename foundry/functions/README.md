# Foundry functions (TypeScript v2)

Action functions the operator triggers from Workshop, plus query functions consumed by the edge.

## Action functions (write — function-backed action types)

| Function | Inputs | Effect |
|---|---|---|
| `issueCommand` | `deviceIds: string[]`, `verb`, `params`, `priority`, `expiresAt`, optional `missionId`, optional `supersedes` | Validates `params` against `command.schema.json`. Loops `deviceIds` and writes one `Command` row per device with status `PENDING` in a single `createEditBatch()` so the multi-device write is atomic. |
| `cancelCommand` | `commandId`, `reason` | Sets the target command to `REJECTED` and emits a superseding `ABORT` to the same drone. |
| `sendTextMessage` | `recipientDeviceIds: string[]`, `body`, optional `sessionId`, optional `inReplyToMessageId` | Writes one `TextMessage` row per recipient with `direction=OPERATOR_TO_EDGE`, `ack_status=PENDING`. |
| `assignMission` | `missionId`, `deviceIds: string[]` | Writes `mission-devices` link rows. Issues an `ASSIGN_MISSION` Command to each assigned device carrying `{mission_id, name, system_prompt}` so the edge LLM can install the prompt. |
| `startMission` | `missionId` | Sets `mission.active = true`, `started_at = now()`. |
| `stopMission` | `missionId` | Sets `mission.active = false`, `ended_at = now()`. |

## Query functions (read — exposed via API gateway)

| Function | Inputs | Returns |
|---|---|---|
| `pollCommands` | `droneId: string`, optional `sinceMessageId: string` | `{ commands: CommandEnvelope[], cursor: string }`. Filter: `device_id = droneId AND status = 'PENDING' AND (sinceMessageId is null OR issued_at > <lookup>) AND expires_at > now()`. Edge calls every 2 s by default. **Never writes back** — lifecycle moves on telemetry events only. |
| `droneFleetSummary` | none | One row per drone with `last_seen`, `state`, `current_command_id`, `current_mission_id`. Backs the dashboard header. |

## Multi-device fan-out

`issueCommand` accepts `deviceIds: string[]` and creates N command rows in one `createEditBatch()`. From Workshop, the operator can:

- select a single drone from the chip header (form pre-fills `deviceIds = [selectedDroneId]`)
- multi-select drones (form pre-fills with the selection)
- target a mission (form resolves `deviceIds` from the `mission-devices` link before submit)

Atomic per call: if any single row fails, the whole call fails — so the operator never sees a half-issued command.

## Schema validation

The shared protocol schemas in [../../shared/protocol/schemas/](../../shared/protocol/schemas/) are the source of truth (currently `0.2.0`, includes `ASSIGN_MISSION` verb). The TypeScript build copies them into `dist/schemas/`; functions validate command payloads with `ajv` before any ontology write.

## Endpoint shape (for the edge to call `pollCommands`)

Foundry exposes query functions at:

```
POST {functionsBaseUrl}/{functionApiName}/execute
Authorization: Bearer <token>
Content-Type: application/json

{ "parameters": { "droneId": "uav-01", "sinceMessageId": "..." } }
```

Response: `{ "value": { "commands": [...], "cursor": "..." } }`. The edge `comms/foundry_client.py` matches this shape.

## Notes

No code committed yet — design only. Stubs land in Phase 1.0 (`issueCommand`, `pollCommands`) and Phase 1.1 (the rest).
