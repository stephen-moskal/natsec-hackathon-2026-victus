# Foundry transforms (Python)

PySpark transforms that normalize inbound telemetry into the shapes the ontology expects, and that drive the command lifecycle from telemetry events.

## Pipeline

```
edge POST → HTTPS Listener → raw_telemetry (streaming, raw envelopes)
                                      │
                                      ▼ telemetry_normalized.py
                            telemetry_normalized
                                      │
        ┌─────────────────┬───────────┼──────────────┬──────────────┐
        │                 │           │              │              │
        ▼                 ▼           ▼              ▼              ▼
  drone_state.py   frame_metadata.py  detections.py  reasoning_traces.py  commands_log.py
        │                 │           │              │              │
        ▼                 ▼           ▼              ▼              ▼
  drone_state       frame_metadata   detections    reasoning_traces  commands_log
   (backs `drone`)   (backs           (Phase 2)     (Phase 2)        (backs `command`)
                      `videoFrame`)
```

## Planned transforms

| Transform | Input | Output | Phase | Purpose |
|---|---|---|---|---|
| `telemetry_normalized.py` | `raw_telemetry` | `telemetry_normalized` | 1.1 | Parse envelope, validate `protocol_version` major matches `0`, drop schema-invalid rows, explode `payload` into typed columns. |
| `drone_state.py` | `telemetry_normalized` filtered to `event in (Position, Status)` | `drone_state` | 1.1 | Latest-row-per-`drone_id` projection backing the `drone` ontology object. |
| `frame_metadata.py` | `telemetry_normalized` filtered to `event = FrameThumbnail` | `frame_metadata` | 1.1 | Latest-row-per-`drone_id` projection backing the `videoFrame` ontology object. |
| `commands_log.py` | Foundry-side `commands_outbound` (written by `issueCommand`) joined with `telemetry_normalized` filtered to `event in (CommandAck, MissionEvent)` | `commands_log` | 1.1 | Joined command lifecycle for the `command` ontology object. Computes `status` per the 5-state lifecycle in [../ontology/README.md](../ontology/README.md). Sets `acked_at`, `completed_at`. |
| `detections.py` | `telemetry_normalized` filtered to `event = Detection` | `detections` | 2 | Backs the `detection` ontology object. |
| `reasoning_traces.py` | `telemetry_normalized` filtered to `event = ReasoningTrace` | `reasoning_traces` | 2 | Backs the `reasoningTrace` ontology object. |
| `commands_expire.py` | `commands_log` | `commands_log` (overwrite) | 1.2 | Scheduled batch (every 60 s): flips `PENDING` rows past `expires_at` to `EXPIRED`. Without this, dead commands sit at PENDING forever. |

## Conventions

- Primary keys: `drone_id` for `drone_state` and `frame_metadata` (latest-row); `message_id` everywhere else.
- All timestamps: ISO 8601 UTC, parsed to `TimestampType`.
- GeoPoint output uses `lat,lon` string format (no parens) — ontology binds it as `GeoPoint` type.
- Use `unionByName(allowMissingColumns=True)` if telemetry schemas drift across protocol minor versions.

## Notes

Transform stubs land in Phase 1.1 once the REST listener is producing `raw_telemetry`. No code committed here yet — design only.
