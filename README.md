# VICTUS — Mission-Aware Edge-Based Reasoning

NatSec Hackathon 2026 entry. Track: **Tactical Edge Autonomy**.

## One-line pitch

A single operator commands a swarm of autonomous drones from a backpack-portable edge kit. Each drone runs a small reasoning LLM on an NVIDIA Jetson Orin, ingests its own video, and acts on terse, doctrine-shaped commands sent from a Palantir Foundry orchestrator — even when the link is intermittent.

## Why this matters

Operators in austere environments cannot rely on cloud inference, full-motion video back to a TOC, or low-latency control loops. Today's autonomy is brittle to link loss and command-heavy. We push *intent* to the edge — short, structured commands in a shared military vocabulary — and let an on-board LLM resolve that intent into action against what the drone is actually seeing.

## Phase 1.0 — DONE: end-to-end API bridge live against real Foundry ✅

The bidirectional bridge between the Jetson and Foundry is up and running, validated on real hardware against the real Palantir Foundry tenant.

```
                                   Foundry stack: victus.usw-23.palantirfoundry.com
                                   Ontology: ontology-abe5026d-72be-...
                                   Folder:   /Victus-743ed7/phantomORCHESTRATION-hackathon/

  ┌────────────────────────┐                                    ┌──────────────────────────┐
  │   Operator (Foundry)   │  POST .../actions/                 │   Edge (Jetson Orin)     │
  │                        │   issue-command/apply              │                          │
  │   Issue Command action ├─►   (writes Command row PENDING) ─►│ command_received         │
  │                        │                                    │ (within 2s of issue)     │
  │                        │◄── POST .../objects/command/search │                          │
  │   Search Objects API   │     filter deviceId+status=PENDING │ poll_commands every 2s   │
  │                        │     (every 2s by edge)             │                          │
  │                        │◄── POST .../publishRecords         │ post_telemetry every 5s  │
  │   raw_telemetry stream │     Streams V2 (telemetry + ACKs)  │ + immediate CommandAck   │
  └────────────────────────┘                                    └──────────────────────────┘
```

**One bearer token, three standard Foundry REST APIs.** No HTTPS Listener and no TypeScript v2 query function were needed. See [foundry/README.md](foundry/README.md) for the full RID list and architecture summary.

### Live in Foundry

| Resource | RID / API name |
|---|---|
| Streaming dataset `raw_telemetry` | `ri.foundry.main.dataset.ed8731a7-4d5c-4741-96bb-fcc2f09608cf` |
| Object type `drone` | `ri.ontology.main.object-type.0c191bf4-...` (PK `drone_id`, 13 props) |
| Object type `command` | `ri.ontology.main.object-type.9bda313a-...` (PK `message_id`, 12 props) |
| Action type `issue-command` | `ri.actions.main.action-type.72c1d608-...` (writes a Command row) |
| Link `commands`/`drone` | `ri.ontology.main.relation.d59d5af5-...` (1:N drone → command) |

### Verified end-to-end (last successful test)

```
21:24:12Z  curl issue-command HOLD            → mid 441CBAEA-...   201
21:24:13Z  edge polls Search Objects          → command_received   logged
21:24:13Z  edge ACKs via publishRecords       → mid e408f90e-...   204
21:24:14Z  Foundry shows CommandAck event in raw_telemetry stream
```

Round-trip latency: **~1 second** from operator click to ACK visible.

## Repo layout

```
.
├── docs/                   # Architecture, protocol, hackathon plan, edge API guide
├── foundry/                # Foundry-side code, ontology design, runbook, RIDs
├── edge/                   # NVIDIA Orin Python package (victus_edge)
├── tools/                  # Local Foundry stub (stdlib HTTP server) + Jetson bring-up doc
├── shared/protocol/        # JSON Schemas — wire-format source of truth for both sides
└── data-tmp/               # Seed CSVs uploaded to Foundry
```

### Pointers

- [docs/EDGE_API_GUIDE.md](docs/EDGE_API_GUIDE.md) — comprehensive guide for installing, configuring, and using the edge API (designed so a person or agent can go from cold start to issuing commands without needing other docs)
- [docs/PROTOCOL.md](docs/PROTOCOL.md) — command/telemetry dictionary (8 verbs, 7 events, 5-state command lifecycle)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system architecture, design tenets, latency budget
- [docs/PLAN.md](docs/PLAN.md) — hackathon phasing and success criteria
- [foundry/README.md](foundry/README.md) — Foundry-side: live RIDs, property name conventions, what's built vs pending
- [foundry/WORKSHOP_RUNBOOK.md](foundry/WORKSHOP_RUNBOOK.md) — operator-side runbook (action curl that works today, Workshop module layout for when built)
- [edge/README.md](edge/README.md) — edge-side overview
- [tools/JETSON_BRINGUP.md](tools/JETSON_BRINGUP.md) — quick checklist for setting up a fresh Jetson
- [tools/foundry_stub.py](tools/foundry_stub.py) — stdlib-only Foundry stub for offline development

## How to drive the system today

**Operator side — issue a HOLD command:**
```bash
TOKEN=<foundry-personal-token>
ONTOLOGY=ontology-abe5026d-72be-438c-980f-344a88cff4dc
MID=$(uuidgen)
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EXP=$(date -u -v+1H +"%Y-%m-%dT%H:%M:%SZ")
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://victus.usw-23.palantirfoundry.com/api/v2/ontologies/$ONTOLOGY/actions/issue-command/apply" \
  -d "{\"parameters\":{\"message_id\":\"$MID\",\"device_id\":\"uav-01\",\"mission_id\":\"none\",\"verb\":\"HOLD\",\"params_json\":\"{}\",\"priority\":\"PRIORITY\",\"status\":\"PENDING\",\"issued_at\":\"$NOW\",\"expires_at\":\"$EXP\",\"acked_at\":\"none\",\"completed_at\":\"none\",\"supersedes\":\"none\"}}"
```

**Edge side — start the loop on a Jetson:**
```bash
ssh jetson 'cd ~/victus/edge && source .venv/bin/activate && set -a && source .env && set +a && \
  nohup bash -c "exec python -m victus_edge.main" </dev/null >/tmp/edge.log 2>&1 & disown'
ssh jetson 'tail -f /tmp/edge.log'
```

Within 2 seconds of the operator's curl, the edge log shows the command and emits an ACK back through the telemetry channel.

## What's next (Phase 1.1+)

| Priority | Item | Why |
|---|---|---|
| P0 | Status-update transform | Read `CommandAck` events from `raw_telemetry`, flip the matching `command.status` from PENDING → ACKED. Without this, the operator UI shows commands as PENDING forever. |
| P0 | Workshop dashboard module | Operator-friendly UI: drone chips, command palette, ACKED status indicators. |
| P1 | Multi-device `issueCommand` variant | Take `deviceIds: array<string>` and create N command rows in one batch. |
| P1 | `videoFrame`, `mission`, `textMessage` object types | Phase 2 telemetry plus mission-prompt delivery (`ASSIGN_MISSION` verb already in protocol). |
| P2 | LLM reasoner + vision pipeline on Jetson | Plug Gemma 3 / Qwen2.5-VL into the `_command_poller` dispatch point that currently just logs + ACKs. |
| P2 | Real flight (MAVLink + SITL or hardware) | Currently `autonomy.controller` is a `mock` backend. |

## Tech stack

- **Edge**: Python 3.10+, asyncio, `httpx`, `jsonschema`, `structlog`, `tenacity`. Tested on Jetson Orin DevKit (aarch64, Ubuntu 22.04, kernel 5.15-tegra). Wi-Fi or USB-C tether for connectivity.
- **Foundry**: Streams V2 publishRecords (telemetry), Ontology Search Objects (command poll), Action Apply (issue command). All standard REST APIs, single bearer token. Required scopes: `api:streams-write`, `api:ontologies-read`, `api:ontologies-write`.
- **Protocol**: JSON Schemas at `shared/protocol/schemas/`, version `0.2.0`. 8 command verbs (`SCAN`, `LOITER`, `INVESTIGATE`, `FOLLOW`, `RTB`, `HOLD`, `ABORT`, `ASSIGN_MISSION`), 7 telemetry events (`Position`, `Status`, `Detection`, `ReasoningTrace`, `FrameThumbnail`, `CommandAck`, `MissionEvent`).
