# Edge API Guide

How to install, configure, run, and talk to the VICTUS edge on a Jetson (or any aarch64/x86_64 Linux box with Python 3.10+). This is the canonical reference — both for humans and for autonomous agents that need to operate the API end-to-end.

For the design rationale behind these choices, see [ARCHITECTURE.md](ARCHITECTURE.md). For the formal wire contract, see [PROTOCOL.md](PROTOCOL.md) and the JSON Schemas in [shared/protocol/schemas/](../shared/protocol/schemas/).

---

## 1. What this is

The "edge API" is the bidirectional bridge between an edge device (a drone running a small reasoning loop) and the Foundry orchestrator (the operator's dashboard). The edge is an HTTP **client**, not a server — it dials out for both directions, using only standard Foundry REST APIs and a single bearer token:

- **Outbound (telemetry):** edge POSTs flattened envelopes as records to the **Streams V2 `publishRecords`** endpoint of a streaming dataset (`raw_telemetry`). Position, status, detections, reasoning traces, command acks, and mission events all ride this channel. Each call accepts a batch of records, validated against the dataset schema. Required token scope: `api:streams-write`.
- **Inbound (commands):** edge POSTs to the **Ontology Search Objects** endpoint every ~2 s, filtering for `command` rows with `deviceId == this drone AND status == PENDING`. Local dedup via a `seen_command_ids` set means each command is processed at most once. Required token scope: `api:ontologies-read`.

This combination — Streams V2 + Search Objects — was chosen because it works on every Foundry stack (no enrollment-gated features), uses one bearer token end-to-end, and avoids the need for an HTTPS Listener or TypeScript v2 query function.

Both directions speak the same envelope shape, defined once in [shared/protocol/schemas/](../shared/protocol/schemas/). The edge validates every message it sends *and* every message it receives against those schemas.

```
+----------------------------+         +-----------------------------+
|  Operator (Foundry)        |         |  Drone (Jetson Orin)        |
|                            |  cmd    |                             |
|  Workshop / curl             | ------> |  Reasoner (Phase 2)         |
|  Issue Command action      |         |  victus_edge.main loop      |
|  Search Objects (poll)     | <------ |  Foundry comms client       |
|  Ontology objects          |  tlm    |                             |
+----------------------------+         +-----------------------------+
            ^                                       |
            |       JSON envelopes over HTTPS        |
            +--------- (commands + telemetry) -------+
```

Current protocol version: **0.2.0**. Both sides MUST match the major version. See [§ 10](#10-extending-the-protocol).

---

## 2. Prerequisites

| Requirement | Notes |
|---|---|
| Linux on the edge | Tested on Jetson Orin DevKit (aarch64, Ubuntu 22.04, kernel 5.15-tegra). Should work on any aarch64 or x86_64 Linux. |
| Python 3.10+ | `python3 --version` must report ≥ 3.10. |
| Network reachability to the orchestrator | Edge must be able to make outbound HTTPS to the Listener URL and the Functions URL. No inbound connectivity to the edge required. |
| Internet access during install | Needed for `pip install` (~30 MB). Can be Wi-Fi, Ethernet, USB-C tether, or a wheelhouse copied over. |
| SSH access to the Jetson | For deployment from a workstation. Default Jetson Orin DevKit images ship with `sshd` enabled. |

---

## 3. Setup on the Jetson

A complete cold-start, copy-paste ready. Replace `<jetson-user>` with your Jetson username (set during OOBE).

### 3.1 SSH access (one-time, from your workstation)

Generate a deploy key (no passphrase, dedicated to this Jetson) and install it:

```bash
# Workstation
ssh-keygen -t ed25519 -N "" -f ~/.ssh/jetson_deploy_ed25519 -C "deploy-key-for-jetson"

# Push it to the Jetson (will prompt for password once)
ssh-copy-id -i ~/.ssh/jetson_deploy_ed25519.pub <jetson-user>@<jetson-ip>
```

Add a host alias so subsequent commands don't need `-i` and `-o` flags:

```bash
cat >> ~/.ssh/config <<EOF

Host jetson
  HostName <jetson-ip>
  User <jetson-user>
  IdentityFile ~/.ssh/jetson_deploy_ed25519
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
EOF
```

Smoke-test: `ssh jetson 'whoami; python3 --version'` should print the username and Python version with no password prompt.

> **Why a dedicated deploy key?** If your personal `~/.ssh/id_ed25519` has a passphrase, `BatchMode=yes` (used by automation) can't decrypt it and SSH silently sends a bad signature → "Permission denied". A passphraseless deploy key avoids the whole class of issues.

### 3.2 Push the edge code

From the repo root on your workstation:

```bash
ssh jetson 'mkdir -p ~/victus'
rsync -avz \
  --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' --exclude '*.egg-info' \
  edge shared \
  jetson:~/victus/
```

**Important:** `edge` and `shared` must be sibling directories on the Jetson — *not* merged. The edge's [protocol.py](../edge/src/victus_edge/comms/protocol.py) loads schemas from `<repo-root>/shared/protocol/schemas/`. Use `rsync edge shared jetson:~/victus/` (no trailing slashes on sources).

Verify layout:

```bash
ssh jetson 'ls ~/victus/{edge,shared/protocol/schemas}'
```

Expected output:
```
~/victus/edge:           pyproject.toml  README.md  src  tests
~/victus/shared/protocol/schemas:  command.schema.json  envelope.schema.json  telemetry.schema.json
```

### 3.3 Install Python dependencies

```bash
ssh jetson 'cd ~/victus/edge && python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip && pip install -e .'
```

This pulls `httpx`, `jsonschema`, `pyyaml`, `structlog`, `tenacity`, `uvloop` plus the editable `victus-edge` package. First install on aarch64 takes 1–3 minutes.

> **Survives ssh drops.** If your SSH connection is flaky (e.g. USB-C tether), wrap in `nohup` so the install survives:
> ```bash
> ssh -n jetson 'cd ~/victus/edge && nohup bash -c "python3 -m venv .venv && source .venv/bin/activate && pip install -e . > install.log 2>&1; echo INSTALL_DONE_\$? >> install.log" </dev/null >/dev/null 2>&1 & disown'
> # Poll for completion:
> ssh jetson 'until grep -q INSTALL_DONE ~/victus/edge/install.log; do sleep 5; done; tail -5 ~/victus/edge/install.log'
> ```

### 3.4 Verify imports

```bash
ssh jetson 'cd ~/victus/edge && source .venv/bin/activate && python -c "from victus_edge.comms import protocol, foundry_client, auth; from victus_edge import config, main; print(\"imports ok, proto\", protocol.PROTOCOL_VERSION)"'
```

Expected: `imports ok, proto 0.2.0`. If you see `FileNotFoundError: shared/protocol/schemas/...` you skipped the `shared` rsync — go back to [§ 3.2](#32-push-the-edge-code).

### 3.5 Configure `.env`

Write the runtime config on the Jetson. Every variable is documented inline:

```bash
ssh jetson 'cat > ~/victus/edge/.env' <<'EOF'
# Identity
VICTUS_DRONE_ID=uav-01

# Foundry endpoints
# - Stack URL: the base of every Foundry API call (no trailing slash)
# - Telemetry dataset RID: the streaming dataset for raw_telemetry
# - Telemetry view RID: optional; if blank the latest stream view is used
# - Ontology: API name OR RID of the ontology that holds the command object type
# - Command object type: API name (real Foundry strips the auto-prefix on merge to main)
FOUNDRY_STACK_URL=https://victus.usw-23.palantirfoundry.com
FOUNDRY_TELEMETRY_DATASET_RID=ri.foundry.main.dataset.ed8731a7-4d5c-4741-96bb-fcc2f09608cf
FOUNDRY_TELEMETRY_VIEW_RID=
FOUNDRY_ONTOLOGY=ontology-abe5026d-72be-438c-980f-344a88cff4dc
FOUNDRY_COMMAND_OBJECT_TYPE=command

# Auth (STATIC = bearer token in env; OAUTH = client_credentials grant)
FOUNDRY_AUTH_MODE=STATIC
FOUNDRY_TOKEN=<personal-api-token-with-streams-write-and-ontologies-read>

# Loop tuning
COMMAND_POLL_INTERVAL_S=2.0
POSITION_EMIT_INTERVAL_S=5.0

# Backends (Phase 2 — default to mock)
VICTUS_LLM_BACKEND=mock
VICTUS_VISION_SOURCE=mock
VICTUS_AUTONOMY_BACKEND=mock

# Local state
VICTUS_TELEMETRY_BUFFER_PATH=./runtime/buffer.jsonl
VICTUS_LOG_LEVEL=INFO
EOF
```

For development against the local stub, point `FOUNDRY_STACK_URL` at the Mac (e.g. `http://192.168.55.100:8080`); the dataset RID, ontology, and object type values can be any non-empty placeholders (the stub doesn't validate them). Token can be any string.

Real-Foundry RIDs for this project are tracked in [foundry/README.md](../foundry/README.md). Full env-var reference is in [§ 11](#11-environment-variables-reference).

### 3.6 Run the edge

**Foreground (dev — live logs in your terminal):**

```bash
ssh -t jetson 'cd ~/victus/edge && source .venv/bin/activate && set -a && source .env && set +a && python -m victus_edge.main'
```

Ctrl-C to stop.

**Background (production-style, survives ssh disconnect):**

```bash
ssh -n jetson 'cd ~/victus/edge && source .venv/bin/activate && set -a && source .env && set +a && nohup bash -c "exec python -m victus_edge.main" </dev/null >/tmp/edge.log 2>&1 & disown'

# Tail logs:
ssh jetson 'tail -f /tmp/edge.log'

# Stop:
ssh jetson 'pkill -f victus_edge.main'
```

> **Why the contortion?** A bare `nohup ... &` over ssh keeps the ssh channel open because the child inherits the controlling pty. The combo `ssh -n` (no stdin) + `</dev/null` (close child stdin) + `>/tmp/edge.log 2>&1` (redirect outputs) + `& disown` (orphan from current shell) is the only reliable detachment that lets ssh exit immediately.

### 3.7 Verify the edge is talking

After ~5 s the edge should have emitted its first Position event and started polling. Quick check from the orchestrator:

```bash
# If using the local stub:
curl -s http://127.0.0.1:8080/admin/state | python3 -m json.tool | head -20

# Should show telemetry_count > 0 and recent Position events
```

If `telemetry_count` stays at 0, see [§ 9.4 troubleshooting](#94-common-errors).

---

## 4. The wire protocol — concept

Every message — whether command or telemetry — uses the same outer envelope:

```json
{
  "protocol_version": "0.2.0",
  "message_id": "f4c1...",
  "issued_at": "2026-05-02T18:00:00Z",
  "sender": "drone-uav-01",
  "kind": "command",
  "payload": { ... }
}
```

Schemas:
- [envelope.schema.json](../shared/protocol/schemas/envelope.schema.json) — envelope structure
- [command.schema.json](../shared/protocol/schemas/command.schema.json) — `payload` when `kind=command`
- [telemetry.schema.json](../shared/protocol/schemas/telemetry.schema.json) — `payload` when `kind=telemetry`

**Envelope rules:**
- `protocol_version` must major-match the receiver's. `0.x.y` → only `0.x.y` peers accept.
- `message_id` is a UUID v4. Receivers MUST dedupe on it.
- `issued_at` is ISO 8601 UTC at the sender. Receivers do not require monotonicity (clock skew is normal).
- `sender` is `drone-<id>` for edge → orchestrator, `foundry-orchestrator` (or similar) for orchestrator → edge.
- `kind` is `command` or `telemetry`. There are no other kinds in 0.x.

**Validation:** the edge's [protocol.py](../edge/src/victus_edge/comms/protocol.py) raises `ProtocolError` on any of: wrong protocol major, unknown kind, schema-invalid payload.

---

## 5. Command vocabulary (orchestrator → edge)

Verbs are exhaustive — anything else is rejected with `CommandAck { result: REJECTED, reason: "unknown_verb" }`.

| Verb | Meaning | Required `params` | Phase |
|---|---|---|---|
| `SCAN` | Sweep an area, report detections. | `area` (GeoJSON Polygon), `pattern` ("grid" \| "spiral"), `altitude_m` | 1.0 (handler stub) |
| `LOITER` | Hold position or orbit a point. | `center` (GeoJSON Point), `radius_m`, `altitude_m` | 1.0 |
| `INVESTIGATE` | Move to a target, observe, report. | `target` (GeoJSON Point or `detection_id`), `dwell_s` | 1.0 |
| `FOLLOW` | Track a moving contact. | `contact_id`, `standoff_m`, `altitude_m` | 1.0 |
| `RTB` | Return to base. | optional `base` (GeoJSON Point); defaults to launch point | 1.0 |
| `HOLD` | Stop and hover safely. | none (`{}`) | 1.0 — used as the round-trip smoke command |
| `ABORT` | Cancel current intent and execute safe fallback. | `reason` (string) | 1.0 |
| `ASSIGN_MISSION` | Update the LLM system-prompt fragment for this drone (delivers a mission). | `mission_id`, `name`, `system_prompt`, optional `priority`, `roe_profile` | 0.2.0 added |

**Modifiers** (every command):

| Field | Type | Required | Notes |
|---|---|---|---|
| `drone_id` | string | yes | Receiving drone. |
| `verb` | enum | yes | One of the verbs above. |
| `priority` | enum | yes | `ROUTINE` \| `PRIORITY` \| `IMMEDIATE` \| `FLASH`. Higher preempts lower. |
| `expires_at` | ISO 8601 UTC | yes | After this, the edge falls back to safe behavior. |
| `params` | object | yes | Verb-specific. May be `{}` for `HOLD`. |
| `roe` | string | no | ROE profile id. Edge enforces what it knows; unknown profile → `ABORT`. |
| `supersedes` | UUID | no | Optional `message_id` of a command this one replaces. |

**Example — full command envelope:**

```json
{
  "protocol_version": "0.2.0",
  "message_id": "5b8c9f2e-1a3d-4e7c-9b8a-2f1d6c3e8a5b",
  "issued_at": "2026-05-02T18:00:00Z",
  "sender": "foundry-orchestrator",
  "kind": "command",
  "payload": {
    "drone_id": "uav-01",
    "verb": "SCAN",
    "priority": "PRIORITY",
    "expires_at": "2026-05-02T18:30:00Z",
    "params": {
      "area": { "type": "Polygon", "coordinates": [[[ -71.06, 42.36 ], [ -71.05, 42.36 ], [ -71.05, 42.37 ], [ -71.06, 42.37 ], [ -71.06, 42.36 ]]] },
      "pattern": "grid",
      "altitude_m": 80
    }
  }
}
```

---

## 6. Telemetry vocabulary (edge → orchestrator)

`payload.event` discriminates the type. Per-type fields below.

| Event | Required fields | Meaning |
|---|---|---|
| `Position` | `lat`, `lon`, `alt_m`, optional `heading_deg`/`speed_mps`/`battery_pct` | Periodic state heartbeat. Default cadence: 5 s. |
| `Status` | `state` (enum), optional `flags[]` | Health state: `NOMINAL` \| `DEGRADED` \| `BINGO` (low fuel) \| `WINCHESTER` (sensors out) \| `LINK_LOST`. |
| `Detection` | `detection_id`, `class`, `confidence`, `bbox`, optional `geo`, optional `frame_ref` | Vision detection. Phase 2. |
| `ReasoningTrace` | `command_id`, `decision`, `rationale` (≤500 chars), optional `tokens` | One LLM reasoning step. Phase 2. |
| `FrameThumbnail` | `format` ("jpeg"), `width`, `height`, `b64` | Compressed frame sample. Capped at ~600 KB by the edge to stay under the 1 MB Foundry Listener limit. Phase 2. |
| `CommandAck` | `command_id`, `result` (`ACCEPTED` \| `REJECTED` \| `EXPIRED`), optional `reason` | Acknowledges a received command. Drives the operator-visible `PENDING → ACKED` transition. |
| `MissionEvent` | `event_kind` (`STARTED` \| `COMPLETED` \| `ABORTED` \| `FALLBACK_HOLD`), `command_id` | Lifecycle marker. Drives `ACKED → COMPLETED/ABORTED`. |

**Status lifecycle (operator-visible, derived from `CommandAck` + `MissionEvent` events):**

```
PENDING ──► ACKED ──► COMPLETED
   │           │
   │           └────► ABORTED        (MissionEvent: ABORTED | FALLBACK_HOLD)
   ├──► EXPIRED                       (CommandAck: EXPIRED, or now > expires_at AND PENDING)
   └──► REJECTED                      (CommandAck: REJECTED)
```

`ACKED` is the answer to "did the operator see the command was received?"

---

## 7. Sending commands (operator side)

Two modes: against the local stub for dev, or against real Foundry once the UI work is done.

### 7.1 Against the local stub

The stub at [tools/foundry_stub.py](../tools/foundry_stub.py) exposes an admin endpoint that builds a valid command envelope from a loose payload and queues it for the next poll.

**Inject HOLD (smallest possible command):**

```bash
curl -X POST http://127.0.0.1:8080/admin/inject_command \
  -H 'Content-Type: application/json' \
  -d '{"drone_id":"uav-01","verb":"HOLD"}'
```

Response: `{"ok": true, "message_id": "<uuid>"}`. The edge picks it up within `COMMAND_POLL_INTERVAL_S` (default 2 s) and ACKs immediately.

**Inject SCAN with full params:**

```bash
curl -X POST http://127.0.0.1:8080/admin/inject_command \
  -H 'Content-Type: application/json' \
  -d '{
    "drone_id": "uav-01",
    "verb": "SCAN",
    "priority": "PRIORITY",
    "params": {
      "area": {"type": "Polygon", "coordinates": [[[-71.06, 42.36], [-71.05, 42.36], [-71.05, 42.37], [-71.06, 42.37], [-71.06, 42.36]]]},
      "pattern": "grid",
      "altitude_m": 80
    },
    "expires_in_s": 1800
  }'
```

**Inject ASSIGN_MISSION (delivers an LLM system-prompt fragment to the drone):**

```bash
curl -X POST http://127.0.0.1:8080/admin/inject_command \
  -H 'Content-Type: application/json' \
  -d '{
    "drone_id": "uav-01",
    "verb": "ASSIGN_MISSION",
    "priority": "IMMEDIATE",
    "params": {
      "mission_id": "m-001",
      "name": "Recon Sector 7",
      "system_prompt": "You are tasked with locating a downed aircraft in the search area. Prioritize areas with smoke or visible wreckage. Confirm any contact by orbiting twice and reporting GPS coordinates."
    }
  }'
```

**Inspect stub state (recent telemetry, pending commands per drone):**

```bash
curl -s http://127.0.0.1:8080/admin/state | python3 -m json.tool
```

**Stub admin reference:**

| Method | Path | Body | Purpose |
|---|---|---|---|
| POST | `/admin/inject_command` | `{drone_id, verb?, params?, priority?, expires_in_s?}` | Build a valid command envelope, queue for next poll. Returns `{ok, message_id}`. |
| GET | `/admin/state` | — | Snapshot: `telemetry_count`, recent telemetry, `pending_by_drone`, `served_counts`. |
| GET | `/healthz` | — | Liveness check. |

### 7.2 Against real Foundry

The action type `issue-command` (RID `ri.actions.main.action-type.72c1d608-fbe0-49fb-9e39-bcee55ade3dd`) is live. Operator path:

1. **Workshop button** (when built — see [foundry/WORKSHOP_RUNBOOK.md](../foundry/WORKSHOP_RUNBOOK.md) § 4): click the action, form pre-fills, action runs, Command row written.
2. **Or via curl** (works today, no Workshop required):

```bash
TOKEN=<personal-api-token-with-ontologies-write>
ONTOLOGY=ontology-abe5026d-72be-438c-980f-344a88cff4dc
MID=$(uuidgen)
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EXPIRY=$(date -u -v+1H +"%Y-%m-%dT%H:%M:%SZ")   # macOS; Linux: -d '+1 hour'

curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://victus.usw-23.palantirfoundry.com/api/v2/ontologies/$ONTOLOGY/actions/issue-command/apply" \
  -d "{
    \"parameters\": {
      \"message_id\": \"$MID\",
      \"device_id\": \"uav-01\",
      \"mission_id\": \"none\",
      \"verb\": \"HOLD\",
      \"params_json\": \"{}\",
      \"priority\": \"PRIORITY\",
      \"status\": \"PENDING\",
      \"issued_at\": \"$NOW\",
      \"expires_at\": \"$EXPIRY\",
      \"acked_at\": \"none\",
      \"completed_at\": \"none\",
      \"supersedes\": \"none\"
    }
  }"
```

Expected response: `{"operationId":"ri.actions.main.action....","validation":{"result":"VALID",...}}`. Within ~2 s the edge picks it up.

> **`"none"` placeholder**: All `command` properties are `nullable: false`, so empty values would fail validation. The convention is the literal string `"none"` for any optional field you don't want to set (`mission_id`, `acked_at`, `completed_at`, `supersedes`). Any non-empty string works; `"none"` is the convention used everywhere in this project for consistency.

### 7.3 Behind the scenes — what the edge sees

The action writes a Command row to `commands_v3` (`status=PENDING`). The edge's poll hits:

```
POST {stack}/api/v2/ontologies/{ontology}/objects/command/search
{
  "where": {
    "type": "and",
    "value": [
      { "type": "eq", "field": "deviceId", "value": "uav-01" },
      { "type": "eq", "field": "status",   "value": "PENDING" }
    ]
  },
  "orderBy": { "fields": [{ "field": "messageId", "direction": "asc" }] },
  "pageSize": 50
}
```

Response shape:
```json
{
  "data": [
    {
      "__primaryKey": "...", "__rid": "...", "__apiName": "command", "__title": "HOLD",
      "messageId": "441CBAEA-...", "deviceId": "uav-01", "verb": "HOLD",
      "paramsJson": "{}", "priority": "PRIORITY", "status": "PENDING",
      "issuedAt": "2026-05-02T22:18:50Z", "expiresAt": "2026-05-02T23:18:50Z",
      "missionId": "none", "ackedAt": "none", "completedAt": "none", "supersedes": "none"
    }
  ],
  "totalCount": "1"
}
```

**camelCase API names**: Foundry auto-converts snake_case property IDs to camelCase API names at deploy time (e.g. `device_id → deviceId`, `params_json → paramsJson`, `lat → latitude`). The edge's [foundry_client.py](../edge/src/victus_edge/comms/foundry_client.py) translates at the HTTP boundary; the wire envelope keeps snake_case throughout. See the property name table in [foundry/README.md](../foundry/README.md).

---

## 8. Receiving commands (edge side)

### 8.1 Where commands arrive

The poll loop lives in [edge/src/victus_edge/main.py](../edge/src/victus_edge/main.py) `_command_poller`. Every `COMMAND_POLL_INTERVAL_S`:

1. Calls `FoundryClient.poll_commands(cursor)` — POST to `${FOUNDRY_STACK_URL}/api/v2/ontologies/${FOUNDRY_ONTOLOGY}/objects/${FOUNDRY_COMMAND_OBJECT_TYPE}/search` with a `where` clause filtering on `deviceId == this drone AND status == PENDING`.
2. Server returns `{data: [{...command object...}, ...], totalCount: "..."}`.
3. Each ontology object is converted to a wire `Envelope` via `_object_to_envelope()` — translating camelCase API names (`messageId`, `deviceId`, `paramsJson`) back to snake_case envelope fields. The result is validated through `protocol.validate()` (raises `ProtocolError` on schema/version mismatch — invalid envelopes are dropped + logged, not ACKed).
4. Local dedup: the `_seen_command_ids` set drops any `messageId` already processed (so the same PENDING row isn't re-emitted on every poll).
5. Edge logs the command and immediately ACKs with `result=ACCEPTED` via `client.ack_command(message_id, "ACCEPTED")` — which goes back through the Streams V2 publishRecords path as a `CommandAck` event.

### 8.2 Handler hook (Phase 1.0 placeholder)

Currently `_command_poller` only logs + ACKs. To plug in actual handling (Phase 2), modify the loop in [main.py](../edge/src/victus_edge/main.py):

```python
async def _command_poller(client: FoundryClient, cfg: Config) -> None:
    cursor: str | None = None
    while True:
        envelopes = await client.poll_commands(cursor)
        for env in envelopes:
            log.info("command_received", message_id=env.message_id, verb=env.payload.get("verb"), params=env.payload.get("params"))
            await client.ack_command(env.message_id, result="ACCEPTED")
            cursor = env.message_id

            # ── plug your handler in here ──────────────────────────
            # e.g. push to a queue consumed by the reasoner, or:
            #   match env.payload["verb"]:
            #     case "HOLD":            await autonomy.safe_fallback()
            #     case "ASSIGN_MISSION":  reasoner.set_prompt(env.payload["params"]["system_prompt"])
            #     case "SCAN":            await autonomy.execute({"do": "scan", **env.payload["params"]})
            #     ...
            # ───────────────────────────────────────────────────────
        await asyncio.sleep(cfg.command_poll_interval_s)
```

The reasoner and autonomy modules are stubs (`NotImplementedError`) until Phase 2.

### 8.3 ACK semantics

- **`ACCEPTED`** — edge has the command, it's well-formed, and the drone is in a state to act on it.
- **`REJECTED`** — edge refuses (unknown verb, invalid params for verb, conflicting ROE). Include a `reason` string. The operator sees the command flip to `REJECTED`.
- **`EXPIRED`** — edge picked it up after `expires_at` had passed. Send this only if the edge is doing the expiry check itself; the orchestrator-side scheduled transform will also catch unACKed expired commands.

Emit ACK via `client.ack_command(message_id, "ACCEPTED")` — convenience method that wraps `encode_telemetry(event="CommandAck", fields={...})` + `post_telemetry`.

---

## 9. Emitting telemetry (edge side)

### 9.1 The streamlined API

Every telemetry event flows through the same two-step pipeline:

```python
from victus_edge.comms.protocol import encode_telemetry

env = encode_telemetry(
    sender=f"drone-{cfg.drone_id}",
    event="Position",
    fields={
        "lat": 42.3601,
        "lon": -71.0589,
        "alt_m": 100.0,
        "heading_deg": 90.0,
        "speed_mps": 0.0,
        "battery_pct": 95.0,
    },
)
await client.post_telemetry([env])
```

`encode_telemetry()` builds the envelope, sets `protocol_version`/`message_id`/`issued_at`/`kind` for you, validates against the schema, and returns the dict ready for the wire. `post_telemetry()` POSTs each envelope to the listener with retry-on-5xx (via `tenacity`) and connection-failure logging.

### 9.2 Event-by-event examples

**Position** (heartbeat — emit every `POSITION_EMIT_INTERVAL_S`):
```python
encode_telemetry("drone-uav-01", "Position", {
    "lat": 42.3601, "lon": -71.0589, "alt_m": 100.0,
    "heading_deg": 90.0, "speed_mps": 12.5, "battery_pct": 85.0,
})
```

**Status** (emit on state transitions):
```python
encode_telemetry("drone-uav-01", "Status", {"state": "DEGRADED", "flags": ["IMU_DRIFT"]})
```

**Detection** (Phase 2 — vision pipeline):
```python
encode_telemetry("drone-uav-01", "Detection", {
    "detection_id": str(uuid.uuid4()),
    "class": "person",
    "confidence": 0.91,
    "bbox": [120, 80, 64, 128],
    "geo": {"lat": 42.3603, "lon": -71.0591},
    "frame_ref": "frame-2026-05-02T18:00:05",
})
```

**ReasoningTrace** (Phase 2 — LLM step):
```python
encode_telemetry("drone-uav-01", "ReasoningTrace", {
    "command_id": "5b8c9f2e-1a3d-4e7c-9b8a-2f1d6c3e8a5b",
    "decision": "approach_target",
    "rationale": "Detected high-confidence person at NE corner of search area; closing to 30m for verification.",
    "tokens": 142,
})
```

**FrameThumbnail** (Phase 2 — periodic frame sample, ≤600 KB encoded):
```python
import base64
jpeg_bytes = ...  # from vision pipeline, capped at 1280x720 quality 75
encode_telemetry("drone-uav-01", "FrameThumbnail", {
    "format": "jpeg",
    "width": 1280, "height": 720,
    "b64": base64.b64encode(jpeg_bytes).decode("ascii"),
})
```

**CommandAck** (use the convenience method instead):
```python
await client.ack_command("5b8c9f2e-...", result="ACCEPTED")
```

**MissionEvent** (lifecycle marker):
```python
encode_telemetry("drone-uav-01", "MissionEvent", {
    "command_id": "5b8c9f2e-...",
    "event_kind": "COMPLETED",
})
```

### 9.3 Direct HTTP (bypassing the Python library)

The Streams V2 endpoint accepts records that match the streaming dataset's schema (not the wire envelope shape directly). The edge flattens envelopes into records before POSTing. From a shell:

```bash
curl -X POST \
  -H "Authorization: Bearer $FOUNDRY_TOKEN" \
  -H 'Content-Type: application/json' \
  "$FOUNDRY_STACK_URL/api/v2/highScale/streams/datasets/$FOUNDRY_TELEMETRY_DATASET_RID/streams/master/publishRecords" \
  -d '{
    "records": [{
      "protocol_version": "0.2.0",
      "message_id": "11111111-2222-3333-4444-555555555555",
      "issued_at": "2026-05-02T18:00:00Z",
      "sender": "drone-uav-01",
      "kind": "telemetry",
      "event": "Status",
      "payload_json": "{\"event\":\"Status\",\"state\":\"NOMINAL\"}"
    }]
  }'
```

Expected: HTTP 204 No Content. This is useful for smoke-testing connectivity from a host that doesn't have the edge package installed.

---

## 10. Operations runbook

### 10.1 Tail logs

```bash
# Edge stdout/stderr (background-mode):
ssh jetson 'tail -f /tmp/edge.log'

# Stub server log (on the orchestrator host):
tail -f /tmp/stub.log
```

The edge uses [structlog](https://www.structlog.org) — every log line is structured key/value (e.g. `command_received message_id=... verb=HOLD params={}`).

### 10.2 Stop / restart the edge

```bash
ssh jetson 'pkill -f victus_edge.main'
# Restart:
ssh -n jetson 'cd ~/victus/edge && source .venv/bin/activate && set -a && source .env && set +a && nohup bash -c "exec python -m victus_edge.main" </dev/null >/tmp/edge.log 2>&1 & disown'
```

### 10.3 Switch from stub to real Foundry

Edit `~/victus/edge/.env` on the Jetson — swap five vars, restart:

```bash
ssh jetson 'sed -i \
  -e "s|^FOUNDRY_STACK_URL=.*|FOUNDRY_STACK_URL=https://victus.usw-23.palantirfoundry.com|" \
  -e "s|^FOUNDRY_TELEMETRY_DATASET_RID=.*|FOUNDRY_TELEMETRY_DATASET_RID=ri.foundry.main.dataset.ed8731a7-4d5c-4741-96bb-fcc2f09608cf|" \
  -e "s|^FOUNDRY_ONTOLOGY=.*|FOUNDRY_ONTOLOGY=ontology-abe5026d-72be-438c-980f-344a88cff4dc|" \
  -e "s|^FOUNDRY_COMMAND_OBJECT_TYPE=.*|FOUNDRY_COMMAND_OBJECT_TYPE=command|" \
  -e "s|^FOUNDRY_TOKEN=.*|FOUNDRY_TOKEN=<your-foundry-personal-token>|" \
  ~/victus/edge/.env'
ssh jetson 'pkill -f victus_edge.main'
ssh -n jetson 'cd ~/victus/edge && source .venv/bin/activate && set -a && source .env && set +a && nohup bash -c "exec python -m victus_edge.main" </dev/null >/tmp/edge.log 2>&1 & disown'
```

The on-the-wire shapes are identical between stub and real Foundry (the stub mirrors Streams V2 publishRecords + Search Objects exactly, including camelCase property names) — no edge code changes needed.

### 10.4 Common errors

| Symptom | Likely cause | Fix |
|---|---|---|
| `RuntimeError: required env var not set: VICTUS_DRONE_ID` | `.env` not sourced before `python -m victus_edge.main`. | Use `set -a && source .env && set +a` before the run command. |
| `FileNotFoundError: shared/protocol/schemas/...` | `shared/` was not rsync'd alongside `edge/`. | Re-run rsync per [§ 3.2](#32-push-the-edge-code) — both as siblings, no trailing slashes. |
| `ProtocolError: protocol major mismatch` | Edge and orchestrator on different protocol majors. | Check `protocol.PROTOCOL_VERSION` on both sides; bump and redeploy together. |
| `ProtocolError: command payload invalid: <verb> is not one of [...]` | Orchestrator sent an unknown verb. | Either add the verb to `command.schema.json` (minor bump) or reject. |
| Edge logs lots of `httpx.ConnectError` | Listener / functions URL unreachable. | From the Jetson: `curl -v $FOUNDRY_LISTENER_URL`. Check firewall, VPN, network. |
| Edge gets 401 / 403 | Token expired or missing project scope. | Re-issue Foundry token (must have action-execute on `issue-command` and read on the streaming dataset). |
| Edge never sees an injected command | Two stubs running on the orchestrator (one received the inject, the other is being polled). | `lsof -nP -iTCP:8080 -sTCP:LISTEN` on the orchestrator; kill duplicates. |
| `ssh jetson` works but `ssh ... 'cmd'` returns immediately empty / 255 | Quoting issue (single quotes inside Bash tool got stripped). | Pipe the script via stdin: `cat <<EOF \| ssh jetson bash -s` |
| Background `nohup` over ssh keeps ssh hanging | Child process inherits ssh's pty. | Use `ssh -n` + `</dev/null >file 2>&1 & disown` — see [§ 3.6](#36-run-the-edge). |

### 10.5 Network bring-up tips

**USB-C tether (Jetson Orin DevKit):** Default IP layout is Jetson `192.168.55.1`, host `192.168.55.100`. If macOS Internet Sharing is on, en11 may lose 192.168.55.100 (host gets put on a `bridge100` instead). Turn off Internet Sharing if you need the original 55.x range.

**Wi-Fi from the Jetson:**
```bash
ssh jetson 'sudo nmcli device wifi connect "<SSID>" password "<password>" ifname wlP1p1s0'
```
Won't help reach the orchestrator if the orchestrator is on a guest/event network with **client isolation** enabled (most coffee shops, event Wi-Fi). USB-C tether is reliable; Wi-Fi may not be.

---

## 11. Environment variables reference

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `VICTUS_DRONE_ID` | yes | — | Stable identity. Becomes `sender = "drone-${VICTUS_DRONE_ID}"`. |
| `FOUNDRY_STACK_URL` | yes | — | Foundry stack base URL (no trailing slash). E.g. `https://victus.usw-23.palantirfoundry.com`. |
| `FOUNDRY_TELEMETRY_DATASET_RID` | yes | — | Streaming dataset RID for `raw_telemetry`. Edge POSTs records to this dataset's `publishRecords` endpoint. |
| `FOUNDRY_TELEMETRY_VIEW_RID` | no | (latest) | Streams V2 view RID. If unset, the latest view on the master branch is used (recommended). |
| `FOUNDRY_ONTOLOGY` | yes | — | Ontology API name OR RID (e.g. `ontology-abe5026d-72be-438c-980f-344a88cff4dc`). |
| `FOUNDRY_COMMAND_OBJECT_TYPE` | yes | — | API name of the Command object type (e.g. `command`; Foundry auto-strips the namespace prefix on merge to main). |
| `FOUNDRY_AUTH_MODE` | no | `STATIC` | `STATIC` (bearer in env) or `OAUTH` (client_credentials grant). |
| `FOUNDRY_TOKEN` | yes if STATIC | — | Bearer token. Required scopes: `api:streams-write`, `api:ontologies-read`, `api:ontologies-write` (the last only if also issuing actions from this token). |
| `FOUNDRY_OAUTH_TOKEN_URL` | yes if OAUTH | — | OAuth token endpoint. |
| `FOUNDRY_CLIENT_ID` | yes if OAUTH | — | OAuth client id. |
| `FOUNDRY_CLIENT_SECRET` | yes if OAUTH | — | OAuth client secret. |
| `COMMAND_POLL_INTERVAL_S` | no | `2.0` | How often the edge polls for new commands. |
| `POSITION_EMIT_INTERVAL_S` | no | `5.0` | How often the edge emits Position events. |
| `VICTUS_LLM_BACKEND` | no | `mock` | `llama_cpp_server` \| `vllm` \| `mock`. Phase 2. |
| `VICTUS_LLM_MODEL_PATH` | no | — | Path/URL to model. Phase 2. |
| `VICTUS_VISION_SOURCE` | no | `mock` | `webcam:0` \| `file:...` \| `gst:<pipeline>` \| `mock`. Phase 2. |
| `VICTUS_AUTONOMY_BACKEND` | no | `mock` | `sitl` \| `mock`. Phase 2. |
| `VICTUS_TELEMETRY_BUFFER_PATH` | no | `./runtime/buffer.jsonl` | Offline buffer path (Phase 1.1). |
| `VICTUS_LOG_LEVEL` | no | `INFO` | Python logging level. |

---

## 12. Extending the protocol

### 12.1 Add a new verb

1. Edit [shared/protocol/schemas/command.schema.json](../shared/protocol/schemas/command.schema.json) — add to `properties.verb.enum`.
2. Bump `$id` minor: `0.2.0 → 0.3.0`. Bump in [envelope.schema.json](../shared/protocol/schemas/envelope.schema.json) and [telemetry.schema.json](../shared/protocol/schemas/telemetry.schema.json) too (keep all three at the same version).
3. Bump `PROTOCOL_VERSION` in [edge/src/victus_edge/comms/protocol.py](../edge/src/victus_edge/comms/protocol.py).
4. Update the changelog in [docs/PROTOCOL.md](PROTOCOL.md).
5. Add a handler branch in `_command_poller` (or wherever you dispatch verbs).
6. **Both sides redeploy together.** Major versions must match.

### 12.2 Add a new telemetry event

1. Edit [shared/protocol/schemas/telemetry.schema.json](../shared/protocol/schemas/telemetry.schema.json) — add the event name to the top-level `event.enum` and append a new entry to `oneOf` describing its required fields.
2. Bump versions per [§ 12.1](#121-add-a-new-verb).
3. Add an emitter (call site that builds + posts the new event).
4. Add a consumer transform on the orchestrator side that projects the new event into an ontology object.

### 12.3 Versioning rules

- **Major bump** (`0.x → 1.x` or `1.x → 2.x`): breaking change. Required field added / typed differently / removed. Both sides MUST be at the same major. Edge rejects mismatched-major messages.
- **Minor bump** (`0.2.0 → 0.3.0`): additive. New verb, new event type, new optional field. Old code treats unknown verbs as `REJECTED` but doesn't crash.
- **Patch bump**: documentation / wording only. No on-the-wire change.

---

## 13. Cheatsheet

**Setup (one-time):**
```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/jetson_deploy_ed25519
ssh-copy-id -i ~/.ssh/jetson_deploy_ed25519.pub <user>@<jetson-ip>
# edit ~/.ssh/config to add 'jetson' alias (see § 3.1)
rsync -avz edge shared jetson:~/victus/
ssh jetson 'cd ~/victus/edge && python3 -m venv .venv && source .venv/bin/activate && pip install -e .'
# write .env per § 3.5
```

**Start the orchestrator-side stub (dev only):**
```bash
python3 tools/foundry_stub.py --port 8080
```

**Start the edge:**
```bash
ssh -n jetson 'cd ~/victus/edge && source .venv/bin/activate && set -a && source .env && set +a && nohup bash -c "exec python -m victus_edge.main" </dev/null >/tmp/edge.log 2>&1 & disown'
```

**Issue a command against the local stub (operator):**
```bash
curl -X POST http://127.0.0.1:8080/admin/inject_command \
  -H 'Content-Type: application/json' \
  -d '{"drone_id":"uav-01","verb":"HOLD"}'
```

**Issue a command against real Foundry (operator):**
```bash
TOKEN=...; ONTOLOGY=ontology-abe5026d-72be-438c-980f-344a88cff4dc
MID=$(uuidgen); NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ"); EXP=$(date -u -v+1H +"%Y-%m-%dT%H:%M:%SZ")
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  "https://victus.usw-23.palantirfoundry.com/api/v2/ontologies/$ONTOLOGY/actions/issue-command/apply" \
  -d "{\"parameters\":{\"message_id\":\"$MID\",\"device_id\":\"uav-01\",\"mission_id\":\"none\",\"verb\":\"HOLD\",\"params_json\":\"{}\",\"priority\":\"PRIORITY\",\"status\":\"PENDING\",\"issued_at\":\"$NOW\",\"expires_at\":\"$EXP\",\"acked_at\":\"none\",\"completed_at\":\"none\",\"supersedes\":\"none\"}}"
```

**Tail edge logs:**
```bash
ssh jetson 'tail -f /tmp/edge.log'
```

**Inspect orchestrator state:**
```bash
curl -s http://127.0.0.1:8080/admin/state | python3 -m json.tool
```

**Stop the edge:**
```bash
ssh jetson 'pkill -f victus_edge.main'
```

---

## 14. Where things live

| File | Purpose |
|---|---|
| [shared/protocol/schemas/](../shared/protocol/schemas/) | Wire format — single source of truth |
| [edge/src/victus_edge/main.py](../edge/src/victus_edge/main.py) | Event loop (poller + emitter) |
| [edge/src/victus_edge/comms/protocol.py](../edge/src/victus_edge/comms/protocol.py) | Encode / decode / validate envelopes |
| [edge/src/victus_edge/comms/foundry_client.py](../edge/src/victus_edge/comms/foundry_client.py) | HTTP client (post_telemetry, poll_commands, ack_command) |
| [edge/src/victus_edge/comms/auth.py](../edge/src/victus_edge/comms/auth.py) | TokenProvider (STATIC + OAUTH) |
| [edge/src/victus_edge/config.py](../edge/src/victus_edge/config.py) | Env-var loader |
| [edge/.env.example](../.env.example) | All env vars, annotated |
| [tools/foundry_stub.py](../tools/foundry_stub.py) | Local Foundry stub (stdlib only, no deps) |
| [tools/JETSON_BRINGUP.md](../tools/JETSON_BRINGUP.md) | Quick bring-up checklist (this guide is the comprehensive version) |
| [foundry/WORKSHOP_RUNBOOK.md](../foundry/WORKSHOP_RUNBOOK.md) | UI runbook for the Foundry-side resources MCP can't create |
| [docs/PROTOCOL.md](PROTOCOL.md) | Formal protocol spec + changelog |
| [docs/ARCHITECTURE.md](ARCHITECTURE.md) | System architecture, design tenets, latency budget |
