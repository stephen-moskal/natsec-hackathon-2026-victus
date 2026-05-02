# Foundry-side runbook — Phase 1.0 round-trip

This is the live, validated configuration. The bidirectional bridge between the Jetson edge and Foundry is up and running using **standard Foundry REST APIs** — no HTTPS Listener and no TypeScript v2 query function were needed.

> **Earlier drafts of this runbook** called for an HTTPS Listener + a TS v2 `pollCommands` function. After investigation, the cleaner path turned out to be Streams V2 + Ontology Search Objects: both use the same Foundry bearer-token auth that we already had, and neither requires enrollment-gated features or a code repository. This document reflects the path we actually built.

---

## 1. Architecture in one diagram

```
                           Foundry stack: https://victus.usw-23.palantirfoundry.com
                           Ontology API name: ontology-abe5026d-72be-438c-980f-344a88cff4dc
                           Folder: /Victus-743ed7/phantomORCHESTRATION-hackathon/orchestration-data/

  ┌────────────────────────┐                                    ┌─────────────────────────────────────┐
  │   Operator (Foundry)   │                                    │   Edge (Jetson, victus_edge.main)   │
  │                        │   POST /api/v2/ontologies/{O}/     │                                     │
  │   Issue Command action ├──   actions/issue-command/apply  ─►│ Command row                         │
  │   (writes Command row) │                                    │ in commands_v3 (status=PENDING)     │
  │                        │                                    │                                     │
  │                        │◄── POST /api/v2/ontologies/{O}/  ──┤ poll_commands every 2s              │
  │                        │     objects/command/search          │ (filter: deviceId+status=PENDING)  │
  │                        │     where deviceId & status=PENDING │                                     │
  │                        │                                    │ → command_received → ACK            │
  │                        │                                    │                                     │
  │                        │◄── POST /api/v2/highScale/streams ──┤ post_telemetry every 5s + ACK     │
  │   raw_telemetry        │     /datasets/{rid}/streams/master/ │                                     │
  │   streaming dataset    │     publishRecords                  │                                     │
  └────────────────────────┘                                    └─────────────────────────────────────┘
```

All three calls use the **same** Foundry bearer token. Required token scopes: `api:streams-write` + `api:ontologies-read` + `api:ontologies-write`.

---

## 2. What's already built (live)

| Resource | RID / API name |
|---|---|
| Streaming dataset `raw_telemetry` | `ri.foundry.main.dataset.ed8731a7-4d5c-4741-96bb-fcc2f09608cf` |
| Backing dataset `drone_state_v3` | `ri.foundry.main.dataset.213600e9-5eff-40d1-89c2-dc0548ba7aca` |
| Backing dataset `commands_v3` | `ri.foundry.main.dataset.44e4dd0d-e444-4ace-9121-ba30d26fb64f` |
| Object type `drone` | `ri.ontology.main.object-type.0c191bf4-db2f-459c-85c3-1834fa62affa` |
| Object type `command` | `ri.ontology.main.object-type.9bda313a-b7aa-4c45-8341-85bd627e59ae` |
| Link type `commands`/`drone` | `ri.ontology.main.relation.d59d5af5-9d4b-4f0c-bac2-aaac748d1c36` |
| Action type `issue-command` | `ri.actions.main.action-type.72c1d608-fbe0-49fb-9e39-bcee55ade3dd` |

Created via the Palantir MCP tools (datasets via `create_and_write_to_foundry_dataset`, ontology resources via `create_or_update_foundry_*` on a global branch, then merged via `create_global_proposal` + UI approval). No UI clicks required for any of the above.

---

## 3. How to issue a command (operator side, today)

Until the Workshop module is built, the operator path is a `curl` against the action API.

```bash
TOKEN=<your-foundry-personal-token>   # scoped api:ontologies-write
ONTOLOGY=ontology-abe5026d-72be-438c-980f-344a88cff4dc
MID=$(uuidgen)
NOW=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EXPIRY=$(date -u -v+1H +"%Y-%m-%dT%H:%M:%SZ")   # macOS; on Linux: date -u -d '+1 hour' +...

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

Expected response: `{"operationId":"ri.actions.main.action....","validation":{"result":"VALID",...}}`. Within ~2 s the edge picks it up; the edge log will show:

```
command_received message_id=... verb=HOLD params={}
```

> **`"none"` is not a magic word, just a chosen sentinel.** All `command` properties are `nullable: false`, so empty values would fail validation. The `"none"` placeholder is the convention; any non-empty string works.

### Verify the command landed in the ontology

```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  "https://victus.usw-23.palantirfoundry.com/api/v2/ontologies/$ONTOLOGY/objects/command/search" \
  -d '{"where":{"type":"eq","field":"deviceId","value":"uav-01"},"pageSize":5}' | python3 -m json.tool
```

Returns the row(s) with `verb`, `status`, `messageId`, etc. **Note the camelCase property names** (Foundry auto-converted from snake_case at deploy time).

### Verify telemetry landed in the streaming dataset

Telemetry takes ~few minutes to flush from the hot stream buffer to the cold backing dataset. To confirm the edge is publishing:

```bash
# Hot path (immediate): hit the stream's read endpoint, OR
# Cold path (after ~5 min flush): SQL the backing dataset
```

Or just check the edge process log for `publishRecords ... 204 No Content` lines (confirmed receipt).

---

## 4. Workshop module (still pending)

The Workshop dashboard has not been built yet. Recommended layout:

```
+-------------------------------------------------------------+
|  Fleet header: per-drone chips (callsign, state, link)      |
+-----------------------------+-------------------------------+
|                             |  Selected drone:              |
|         Map widget          |   - Status / battery          |
|         (drone positions)   |   - Current command           |
|                             |                               |
|                             |  Command palette:             |
|                             |   [SCAN] [LOITER] [HOLD]      |
|                             |   [INVESTIGATE] [RTB] [ABORT] |
+-----------------------------+-------------------------------+
|  Command list: recent commands for selected drone           |
+-------------------------------------------------------------+
```

**Variables:**
- `selectedDroneId` (string, default `"uav-01"`)
- `fleet` = all `drone` objects
- `selectedDrone` = `fleet` filtered to `droneId == selectedDroneId`
- `recentCommands` = all `command` objects filtered to `deviceId == selectedDroneId`, sorted by `issuedAt desc`

**Issue HOLD button** — wires to action type `issue-command`. Form pre-fills:
- `device_id` ← `selectedDroneId`
- `verb` ← `"HOLD"`
- `params_json` ← `"{}"`
- `priority` ← `"PRIORITY"`
- `status` ← `"PENDING"`
- `message_id` ← `uuid()` Workshop expression
- `issued_at` ← `now()` Workshop expression
- `expires_at` ← `now() + 1 hour`
- All optional fields (`mission_id`, `acked_at`, `completed_at`, `supersedes`) ← `"none"`

The Drone object type has a `lat`/`lon` pair (mapped to API names `latitude`/`longitude`). The Workshop map widget can render directly from these — no extra GeoPoint conversion needed because both are doubles.

---

## 5. Phase 1.1 follow-ups

| Task | Why |
|---|---|
| Status-update transform | Read `CommandAck` events from `raw_telemetry`, flip the matching `command.status` in `commands_v3` from `PENDING` to `ACKED`. Without this, operator-visible status stays `PENDING` forever even after the edge has ACKed. |
| Multi-device `issueCommand` variant | Current action takes a single `device_id`. Operators wanting to fan out to 3+ drones at once will want an action that takes `deviceIds: array<string>` and creates N rows in one batch. |
| `videoFrame` object type | Phase 2 vision work — latest-frame-per-drone projection from `FrameThumbnail` events on `raw_telemetry`. |
| `mission` object type + `assignMission` action | Lets operators define LLM system-prompt fragments and assign them to drones. Edge handles via the `ASSIGN_MISSION` verb (already in protocol 0.2.0). |
