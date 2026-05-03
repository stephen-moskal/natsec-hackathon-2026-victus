# VICTUS — Mission-Aware Edge-Based Reasoning

NatSec Hackathon 2026 entry. Track: **Tactical Edge Autonomy**.

## One-line pitch

A single operator commands a swarm of autonomous drones from a backpack-portable edge kit. Each drone runs a small reasoning LLM on an NVIDIA Jetson Orin, ingests its own video, and acts on terse, doctrine-shaped commands sent from a Palantir Foundry orchestrator — even when the link is intermittent.

## Why this matters

Operators in austere environments cannot rely on cloud inference, full-motion video back to a TOC, or low-latency control loops. Today's autonomy is brittle to link loss and command-heavy. We push *intent* to the edge — short, structured commands in a shared military vocabulary — and let an on-board LLM resolve that intent into action against what the drone is actually seeing.

## Status — Phases 1, 2, 3 done ✅

The full operator → Foundry → edge → Foundry → operator loop is live, including a standalone React UI for fleet monitoring, command issuance, and mission authoring. All three phases are validated against the real Palantir Foundry tenant.

```
                            Foundry stack: victus.usw-23.palantirfoundry.com
                            Ontology: ontology-abe5026d-72be-...
                            Folder:   /Victus-743ed7/phantomORCHESTRATION-hackathon/

 ┌─────────────────────┐    HTTP /api/*    ┌───────────────────┐
 │  Operator browser   │ ◄────────────────►│   Node BFF        │ ◄──── Foundry REST
 │  React + Vite UI    │   localhost:5173  │   localhost:8787  │       (3 endpoints,
 │  • Dashboard        │     (CORS-safe)   │   owns the token  │        single bearer)
 │  • Mission editor   │                   └─────────┬─────────┘
 │  • Command palette  │                             │
 └─────────────────────┘                             ▼
                                          ┌──────────────────────────────────┐
                                          │     Foundry (orchestrator)       │
                                          │                                  │
                                          │  Action Apply ─► Command row     │
                                          │       ▲          (PENDING)       │
                                          │       │                ▲         │
                                          │  create-mission        │ poll    │
                                          │  issue-command         │ every   │
                                          │  assign-mission        │ 2s      │
                                          │                        │         │
                                          │  ◄── Streams V2  ──── ┘         │
                                          │      publishRecords              │
                                          │      raw_telemetry +             │
                                          │      CommandAck                  │
                                          └──────────────────┬───────────────┘
                                                             │
                                                             ▼
                                                ┌──────────────────────────┐
                                                │   Edge (Jetson Orin)     │
                                                │   victus_edge.main       │
                                                │   • poll_commands  2s    │
                                                │   • post_telemetry 5s    │
                                                │   • immediate ACK        │
                                                └──────────────────────────┘
```

**One bearer token, three standard Foundry REST APIs (`Action Apply`, `Search Objects`, `Streams V2 publishRecords`).** No HTTPS Listener and no TypeScript v2 query function were needed. See [foundry/README.md](foundry/README.md) for the full RID list.

### What each phase shipped

| Phase | Scope | Outcome |
|---|---|---|
| **1.0** | Bidirectional API bridge edge ↔ Foundry | Operator `curl issue-command` → edge `command_received` → `CommandAck` in raw_telemetry, all in ~1s |
| **2.0** | React UI + Node BFF + multi-drone command palette | Operator clicks 8 verbs (policy-aligned: `ABORT`/`RTB`/`GOTO`/`ALTITUDE`/`LOITER`/`SEARCH`/`OBSERVE`/`REPORT`/`TRACK`/`IDENTIFY`) on N selected drones, fan-out via `Promise.allSettled` |
| **2.5** | Wire-protocol alignment to `drone_command_policy.json` | Schemas v0.3.0; brevity replies `WILCO`/`UNABLE`/`ROGER`/`STANDBY`; new telemetry events `Sitrep`/`Contact`/`Observation`/`Bingo`/`Nodeloss` |
| **3.0** | `mission` ontology object + author/assign UX | Operator authors a system-prompt body, picks drones, hits Assign → N `ASSIGN_MISSION` commands fire; `CurrentMissionPanel` on each `DroneCard` reflects it within ~3s |

### Live in Foundry

| Resource | RID / API name |
|---|---|
| Streaming dataset `raw_telemetry` | `ri.foundry.main.dataset.ed8731a7-4d5c-4741-96bb-fcc2f09608cf` |
| Backing dataset `drone_state_v3` | `ri.foundry.main.dataset.213600e9-5eff-40d1-89c2-dc0548ba7aca` |
| Backing dataset `commands_v3` | `ri.foundry.main.dataset.44e4dd0d-e444-4ace-9121-ba30d26fb64f` |
| Backing dataset `missions_v1` | `ri.foundry.main.dataset.5c3510f5-decd-4a81-8a3d-7ffe1f80fba9` |
| Object type `drone` | `ri.ontology.main.object-type.0c191bf4-...` (PK `drone_id`, 13 props) |
| Object type `command` | `ri.ontology.main.object-type.9bda313a-...` (PK `message_id`, 12 props) |
| Object type `mission` (api `pzqmccug.mission`) | `ri.ontology.main.object-type.4689d999-c463-4295-b968-ae1e771581d8` (PK `mission_id`, 13 props, `system_prompt` long-text) |
| Action type `issue-command` | `ri.actions.main.action-type.72c1d608-...` |
| Action type `create-mission` | `ri.actions.main.action-type.17fefe30-b91f-4d24-a54e-c9f57812701f` |
| Link `commands`/`drone` | `ri.ontology.main.relation.d59d5af5-...` (1:N drone → command) |

### Verified end-to-end (recent tests)

**Phase 1.0 — single command:**
```
21:24:12Z  curl issue-command HOLD            → mid 441CBAEA-...   201
21:24:13Z  edge polls Search Objects          → command_received   logged
21:24:13Z  edge ACKs via publishRecords       → mid e408f90e-...   204
21:24:14Z  Foundry shows CommandAck event in raw_telemetry stream
```

**Phase 3.0 — UI mission creation + assign:**
```
01:26:06Z  POST /api/missions "Testing Hackthon"   → mission row 8ead8355-... in missions_v1
01:26:12Z  POST /api/assign-mission to uav-02,uav-03 → 2× ASSIGN_MISSION commands PENDING
           UI's CurrentMissionPanel on BRAVO + CHARLIE shows "Testing Hackthon" within 3s
```

Round-trip latency: **~1 second** operator click → ACK; **~3 seconds** UI reflects new mission.

## Repo layout

```
.
├── docs/                   # Architecture, protocol, hackathon plan, edge API guide
├── foundry/                # Foundry-side code, ontology design, runbook, RIDs
├── edge/                   # NVIDIA Orin Python package (victus_edge)
├── ui/                     # React + Vite operator dashboard (Phases 2 + 3)
├── bff/                    # Tiny Node BFF that owns the Foundry token (Phase 2)
├── tools/                  # Local Foundry stub (stdlib HTTP server) + Jetson bring-up doc
├── shared/protocol/        # JSON Schemas — wire-format source of truth for both sides
└── data-tmp/               # Seed CSVs uploaded to Foundry
```

### Pointers

- [docs/EDGE_API_GUIDE.md](docs/EDGE_API_GUIDE.md) — comprehensive guide for installing, configuring, and using the edge API (designed so a person or agent can go from cold start to issuing commands without needing other docs)
- [docs/PROTOCOL.md](docs/PROTOCOL.md) — command/telemetry dictionary (10 policy verbs + `ASSIGN_MISSION`, 12 telemetry events, drone brevity replies `WILCO`/`UNABLE`/`ROGER`/`STANDBY`)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system architecture, design tenets, latency budget
- [docs/PLAN.md](docs/PLAN.md) — hackathon phasing and success criteria
- [foundry/README.md](foundry/README.md) — Foundry-side: live RIDs, property name conventions, what's built vs pending
- [foundry/WORKSHOP_RUNBOOK.md](foundry/WORKSHOP_RUNBOOK.md) — operator-side runbook (action curl that works today, Workshop module layout for when built)
- [ui/README.md](ui/README.md) — React UI quick start, route map, component layout
- [bff/README.md](bff/README.md) — Node BFF quick start and endpoint reference
- [edge/README.md](edge/README.md) — edge-side overview
- [tools/JETSON_BRINGUP.md](tools/JETSON_BRINGUP.md) — quick checklist for setting up a fresh Jetson
- [tools/foundry_stub.py](tools/foundry_stub.py) — stdlib-only Foundry stub for offline development

## How to drive the system today

The operator workflow is now graphical. Two terminals + a browser, then click around.

**Step 1 — start the BFF (owns the Foundry token):**
```bash
cd bff
cp .env.example .env             # edit FOUNDRY_TOKEN, set MOCK_MODE=false
npm install && npm run dev       # listens on http://localhost:8787
```

**Step 2 — start the UI:**
```bash
cd ui
npm install && npm run dev       # opens http://localhost:5173
```

**Step 3 — start the edge on a Jetson:**
```bash
ssh jetson 'cd ~/victus/edge && source .venv/bin/activate && set -a && source .env && set +a && \
  nohup bash -c "exec python -m victus_edge.main" </dev/null >/tmp/edge.log 2>&1 & disown'
ssh jetson 'tail -f /tmp/edge.log'
```

**Step 4 — click stuff in the browser:**
- **Dashboard** (`/`) — see the fleet, pick drones in the right-side **Command Palette**, choose a verb (`SEARCH`, `OBSERVE`, etc.), edit `params_json`, hit **Send**. Within 2s the Jetson edge logs `command_received` and emits an ACK.
- **Missions** (`/missions`) — author a mission (name + plain-English `system_prompt`). Use the **load example** button to pre-fill a working demo. Pick the new mission in the library, select drones, hit **Assign**. Each `DroneCard`'s **Current Mission** panel reflects it within ~3s.
- **Settings** (`/settings`) — Foundry health, token expiry from JWT `exp` claim.

**Or, drive Foundry directly via curl** (still works — the UI uses the same Action Apply endpoint):
```bash
TOKEN=<foundry-personal-token>
ONTOLOGY=ontology-abe5026d-72be-438c-980f-344a88cff4dc
MID=$(uuidgen); NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ"); EXP=$(date -u -v+1H +"%Y-%m-%dT%H:%M:%SZ")
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://victus.usw-23.palantirfoundry.com/api/v2/ontologies/$ONTOLOGY/actions/issue-command/apply" \
  -d "{\"parameters\":{\"message_id\":\"$MID\",\"device_id\":\"uav-01\",\"mission_id\":\"none\",\"verb\":\"REPORT\",\"params_json\":\"{}\",\"priority\":\"PRIORITY\",\"status\":\"PENDING\",\"issued_at\":\"$NOW\",\"expires_at\":\"$EXP\",\"acked_at\":\"none\",\"completed_at\":\"none\",\"supersedes\":\"none\"}}"
```

## What's next (Phase 4+)

| Priority | Item | Why |
|---|---|---|
| **P0** | **Streaming PySpark transforms** | (1) `drone_state_live` — project latest `Position` event from `raw_telemetry` into `drone_state_v3` so `DroneCard` link dots turn green. (2) `commands_status` — read `CommandAck` events, flip `command.status` PENDING→ACKED so the UI's command list reflects what the edge actually did. Without these, the dashboard shows seed-static data forever. |
| P0 | `last_reasoning` + `last_frame` ontology objects | Latest-row-per-`sender` projections of `ReasoningTrace` and `FrameThumbnail` events. UI's existing `LLMTracePanel` and `VideoPanel` placeholders just need the data source. |
| P1 | Multi-device `issueCommand` variant | Action takes `deviceIds: array<string>` and creates N command rows in one batch (today the UI fans out N single-device calls via `Promise.allSettled`). |
| P1 | LLM reasoner + vision pipeline on Jetson | Plug Gemma 3 / Qwen2.5-VL into the edge's `_command_poller` dispatch point that currently just logs + ACKs. The mission's `system_prompt` is already arriving on the wire. |
| P2 | Real flight (MAVLink + SITL or hardware) | Currently `autonomy.controller` is a `mock` backend. |

## Tech stack

- **Edge**: Python 3.10+, asyncio, `httpx`, `jsonschema`, `structlog`, `tenacity`. Tested on Jetson Orin DevKit (aarch64, Ubuntu 22.04, kernel 5.15-tegra). Wi-Fi or USB-C tether for connectivity.
- **UI**: React 19, Vite 7, TypeScript ~5.9, Tailwind v4 (dark theme), `react-router-dom` 7, plain `fetch` + `useState` (no Redux/zustand).
- **BFF**: Node + Express + TS, `undici` for fetch, `tsx watch` for dev. ~250 LOC. Owns `FOUNDRY_TOKEN` via env so the browser never sees it. Single port (`localhost:8787`), CORS allow-list one origin.
- **Foundry**: Streams V2 `publishRecords` (telemetry), Ontology Search Objects (command/mission poll), Action Apply (`issue-command`, `create-mission`). All standard REST APIs, single bearer token. Required scopes: `api:streams-write`, `api:ontologies-read`, `api:ontologies-write`.
- **Protocol**: JSON Schemas at `shared/protocol/schemas/`, version `0.3.0` — aligned with [drone_command_policy.json](drone_command_policy.json). 11 command verbs (`ABORT`, `RTB`, `GOTO`, `ALTITUDE`, `LOITER`, `SEARCH`, `OBSERVE`, `REPORT`, `TRACK`, `IDENTIFY` from the policy + `ASSIGN_MISSION` for operator missions), 12 telemetry events (`Position`, `Status`, `Detection`, `ReasoningTrace`, `FrameThumbnail`, `CommandAck`, `MissionEvent`, `Sitrep`, `Contact`, `Observation`, `Bingo`, `Nodeloss`). Drone brevity replies: `WILCO` / `UNABLE` / `ROGER` / `STANDBY`.
