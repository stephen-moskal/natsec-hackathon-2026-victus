# Foundry transforms (Python)

PySpark transforms that normalize inbound telemetry into the shapes the ontology expects.

## Planned transforms

| Transform | Input | Output | Purpose |
|---|---|---|---|
| `telemetry_normalized.py` | `raw_telemetry` (streaming, raw JSON envelopes) | `telemetry_normalized` | Parse envelope, validate `protocol_version`, explode `payload` into typed columns, drop schema-invalid rows. |
| `drone_state.py` | `telemetry_normalized` | `drone_state` | Latest-row-per-`drone_id` projection backing the `Drone` ontology object. |
| `detections.py` | `telemetry_normalized` filtered to `event = Detection` | `detections` | Backs the `Detection` ontology object. |
| `reasoning_traces.py` | `telemetry_normalized` filtered to `event = ReasoningTrace` | `reasoning_traces` | Backs the `ReasoningTrace` ontology object. |
| `commands_log.py` | Foundry-side `commands_outbound` + ACKs from `telemetry_normalized` | `commands_log` | Joined command lifecycle for the `Command` ontology object. |

## Conventions

- Primary keys: `drone_id` for `drone_state`; `message_id` everywhere else.
- All timestamps: ISO 8601 UTC, parsed to `TimestampType`.
- Use `unionByName(allowMissingColumns=True)` if telemetry schemas drift across protocol minor versions.

## Notes

Transform stubs will be added in Phase 1 once the REST data source is producing `raw_telemetry`. No code committed here yet — design only.
