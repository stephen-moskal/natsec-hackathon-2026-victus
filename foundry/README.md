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

| Foundry resource | Path / RID (TBD) |
|---|---|
| Project | `/Victus-NatSec-2026/` |
| REST API data source | `victus-edge-ingest` |
| Webhook | `telemetry-inbound` |
| Streaming datasets | `raw_telemetry`, `commands_outbound` |
| Ontology object types | `drone`, `mission`, `command`, `observation`, `detection`, `reasoning-trace` |
| Functions namespace | `victus.orchestrator` |
| Workshop module | `Victus Operator Console` |

Fill in actual RIDs as resources are created.

## Subdirectory READMEs

- [transforms-python/README.md](transforms-python/README.md)
- [functions/README.md](functions/README.md)
- [ontology/README.md](ontology/README.md)
- [workshop/README.md](workshop/README.md)
