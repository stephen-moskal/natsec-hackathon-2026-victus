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

### Created (Phase 1.0 via MCP)

| Foundry resource | RID |
|---|---|
| Stack | `https://victus.usw-23.palantirfoundry.com` |
| Namespace | `Victus-743ed7` (`ri.compass.main.folder.1b5350a4-4ac5-4803-9c21-1c8096941798`) |
| Project folder | `/Victus-743ed7/phantomORCHESTRATION-hackathon` (`ri.compass.main.folder.e5c96633-8b74-4268-bd42-f4d0d2e3ca53`) |
| Data subfolder | `/Victus-743ed7/phantomORCHESTRATION-hackathon/orchestration-data` (`ri.compass.main.folder.bd1b025f-8c76-4cf4-9964-10c5e35ed537`) |
| Ontology | Victus Ontology (`ri.ontology.main.ontology.10d8565f-992c-4cd2-8df5-0328b5d7e46b`) |
| Global branch | `phantom-orchestration-phase1` (`ri.branch..branch.b9f173a4-9ded-4626-94ad-3d8b3be2e472`) |
| Dataset: drone_state_seed | `ri.foundry.main.dataset.7ee6e336-894e-425c-a9f2-776ca3590f01` (3 seed drones) |
| Dataset: commands_seed | `ri.foundry.main.dataset.1d73c313-6efd-4d6b-bc83-3b7e672c8a71` (1 expired seed row) |
| Object type: Drone | `pzqmccug.drone` (PK `drone_id`, backed by drone_state_seed) |
| Object type: Command | `pzqmccug.command` (PK `message_id`, backed by commands_seed) |
| Link type: Drone Commands | `pzqmccug.drone-commands` (1:N drone → command via device_id, RID `ri.ontology.main.relation.aa0a4b48-34ff-4b8c-9c56-f05b4d81ebbb`) |
| Action type: Issue Command | `issue-command` (`ri.actions.main.action-type.fc60ac14-905e-4ec9-b84f-f4d7a18ec760`) — adds a Command row, all properties as parameters |

All ontology resources live on the `phantom-orchestration-phase1` branch. They become visible on main only after a proposal is created and merged via Foundry UI.

### Pending (UI work — see `WORKSHOP_RUNBOOK.md` at repo root)

| Foundry resource | Status |
|---|---|
| HTTPS Listener `telemetry-inbound` → `raw_telemetry` streaming dataset | UI only — Data Connection app |
| TS v2 query function `pollCommands(droneId, sinceMessageId)` | UI / TS code repo |
| Workshop module `Victus Operator Console` | UI only |
| Proposal: merge `phantom-orchestration-phase1` to main | UI only |

## Subdirectory READMEs

- [transforms-python/README.md](transforms-python/README.md)
- [functions/README.md](functions/README.md)
- [ontology/README.md](ontology/README.md)
- [workshop/README.md](workshop/README.md)
