# Foundry functions (TypeScript)

Action functions that the operator triggers from Workshop, plus utility functions consumed by widgets.

## Planned functions

### Action functions (write)

| Function | Inputs | Effect |
|---|---|---|
| `issueCommand` | `droneId`, `verb`, `params`, `priority`, `expiresAt`, optional `supersedes` | Validates against `command.schema.json`, writes a new `Command` ontology object with status `PENDING`, and appends to `commands_outbound`. |
| `cancelCommand` | `commandId`, `reason` | Sets target command status to `CANCELLED` and emits a superseding `ABORT` to the same drone. |
| `setROE` | `droneId`, `roeProfileId` | Updates the drone's active ROE profile; takes effect on next command. |

### Query functions (read)

| Function | Inputs | Returns |
|---|---|---|
| `pollCommands` | `droneId`, `sinceMessageId` | Pending commands for the drone, ordered, since the cursor. Called by the edge. |
| `droneFleetSummary` | none | One row per drone with last-seen, status, current intent. Backs the dashboard header. |

## Schema validation

The shared protocol schemas in [../../shared/protocol/schemas/](../../shared/protocol/schemas/) are the source of truth. The TypeScript build copies them into `dist/schemas/` and the function code validates with `ajv` before any ontology write.

## Notes

No code committed here yet — design only. Stubs will land in Phase 1 alongside the REST data source.
