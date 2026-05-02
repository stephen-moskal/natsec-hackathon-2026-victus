# Foundry UI Runbook — Phase 1.0 round-trip

What MCP couldn't do for us, in the order we need it. Goal: close the loop so an operator click in Workshop becomes a logged command on the edge process within a few seconds, and the command status flips to `ACKED` in Workshop a few seconds after that.

**Pre-requisite:** the four ontology resources from `foundry/README.md` must be visible on the `phantom-orchestration-phase1` global branch (`ri.branch..branch.b9f173a4-9ded-4626-94ad-3d8b3be2e472`). All UI work below should be done **on this branch** — switch to it via the branch picker in the top bar of any Foundry page.

---

## 1. HTTPS Listener — inbound telemetry

Lands edge → Foundry telemetry into a streaming dataset.

1. Foundry → **Data Connection** app → **+ New Source** → **HTTPS Listener**.
2. Save into `/Victus-743ed7/phantomORCHESTRATION-hackathon/orchestration-data/`.
3. **Name:** `telemetry-inbound`.
4. **Output dataset:** create new, name `raw_telemetry`. Type = streaming.
5. **Authentication:**
   - Method: **Basic auth** (or **Header token**, slightly nicer).
   - Generate a random shared secret (e.g. `openssl rand -hex 24`). This is the bearer token the edge will use; copy it.
6. Save and **Enable** the listener. Foundry generates a unique HTTPS URL — copy it.
7. Confirm the URL works: from a terminal,
   ```bash
   curl -X POST "<listener-url>" \
     -H "Authorization: Bearer <shared-secret>" \
     -H "Content-Type: application/json" \
     -d '{"protocol_version":"0.2.0","message_id":"00000000-0000-0000-0000-000000000001","issued_at":"2026-05-02T20:00:00Z","sender":"drone-uav-01","kind":"telemetry","payload":{"event":"Position","lat":42.36,"lon":-71.06,"alt_m":100,"heading_deg":0,"speed_mps":0,"battery_pct":99}}'
   ```
   Within ~30 s, a row should appear in the `raw_telemetry` streaming dataset's preview.

**Edge config:** put the listener URL in `FOUNDRY_LISTENER_URL` and the shared secret in `FOUNDRY_TOKEN` of the edge `.env`.

---

## 2. TypeScript v2 query function — `pollCommands`

Edge polls this every 2 s for new commands addressed to its `drone_id`.

1. Foundry → **Code Repositories** → **+ New Repository** → **TypeScript Functions** template (TS v2).
2. Save into `/Victus-743ed7/phantomORCHESTRATION-hackathon/`. Name: `phantom-orchestration-functions`.
3. Clone the repo locally (Foundry shows the `git clone` URL).
4. Add a function file `src/pollCommands.ts`:

   ```typescript
   import { Command } from "@ontology/sdk"; // generated; SDK package name may differ
   import { Client, Integer } from "@osdk/client";
   import { Function } from "@osdk/functions";

   interface PollResult {
     commands: Command[];
     cursor: string | null;
   }

   export default async function pollCommands(
     client: Client,
     droneId: string,
     sinceMessageId?: string,
   ): Promise<PollResult> {
     const { data } = await client(Command).fetchPage({
       $where: {
         device_id: { $eq: droneId },
         status: { $eq: "PENDING" },
       },
       $orderBy: { message_id: "asc" },
       $pageSize: 50,
     });

     const filtered = sinceMessageId
       ? data.filter(c => c.message_id! > sinceMessageId)
       : data;

     return {
       commands: filtered,
       cursor: filtered.length > 0 ? filtered[filtered.length - 1].message_id! : null,
     };
   }
   ```

5. Generate the OSDK on the branch (Foundry will prompt — accept).
6. Commit, push. Foundry CI builds. Wait for green.
7. Tag a release: `git tag 0.1.0 && git push --tags` (semver, no `v` prefix).
8. **Publish** the function via the Code Repository page → **Publish version**.
9. Find the function's REST endpoint: open the function in Foundry, copy the **API gateway URL**. Strip the function-name suffix to get the base — that's `FOUNDRY_FUNCTIONS_URL` for the edge `.env`. The edge calls `${FOUNDRY_FUNCTIONS_URL}/pollCommands/execute`.

**Smoke test:**
```bash
curl -X POST "${FOUNDRY_FUNCTIONS_URL}/pollCommands/execute" \
  -H "Authorization: Bearer ${FOUNDRY_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"parameters":{"droneId":"uav-01","sinceMessageId":null}}'
```
Should return `{"value":{"commands":[...],"cursor":"..."}}` (probably empty `commands` if none are PENDING).

---

## 3. Workshop module — `Victus Operator Console`

Minimal Phase 1.0 layout: drone chip + Issue HOLD button + command list.

1. Foundry → **Workshop** → **+ New Module**. Save into `/Victus-743ed7/phantomORCHESTRATION-hackathon/`. Name: `Victus Operator Console`. **Switch the module to use the `phantom-orchestration-phase1` branch** (top-right branch picker inside Workshop).
2. Add a **Variable**: `selectedDroneId` (string), default `"uav-01"`.
3. Add a **Drone object set variable**: `fleet` = all `Drone` objects.
4. Add a **Selected drone variable**: `selectedDrone` = `fleet` filtered to `drone_id == selectedDroneId`. Cardinality: single.
5. Add widgets:
   - **Object list** bound to `fleet`. Title column: `callsign`. On click → set `selectedDroneId = clickedRow.drone_id`.
   - **Object card** bound to `selectedDrone`. Show `callsign`, `state`, `lat`, `lon`, `battery_pct`.
   - **Action button**: "Issue HOLD". Configure → action type **Issue Command**. Pre-fill parameters:
     - `device_id` = `selectedDroneId`
     - `message_id` = a UUID expression (Workshop has a `uuid()` function) or a timestamp-based string
     - `verb` = `"HOLD"`
     - `params_json` = `"{}"`
     - `priority` = `"ROUTINE"`
     - `status` = `"PENDING"`
     - `mission_id`, `acked_at`, `completed_at`, `supersedes` = `""` (empty strings — the action requires all fields)
   - **Object table** bound to `Command` filtered by `device_id == selectedDroneId`. Columns: `verb`, `status`, `message_id`. Sort: `message_id desc`. Auto-refresh every 5 s.

When the button is clicked, a new Command row should appear in the table with status `PENDING`. Once the edge process polls and ACKs, status flips to `ACKED` (the ACK path requires the Phase 1.1 `commands_log.py` transform — for Phase 1.0, you can manually run a quick "Modify Command" action to flip status, or just verify the row arrives in the table).

---

## 4. Proposal: merge branch to main

After Phase 1.0 round-trip is green:

1. Foundry top bar → branch picker → `phantom-orchestration-phase1` → **Create proposal**.
2. Title: `VICTUS Phase 1.0 ontology — drone, command, link, issueCommand action`.
3. Reviewers: yourself / teammates.
4. Include the four ontology resources (drone, command, drone-commands, issue-command) plus the listener and function if you want them on main too.
5. Approve & merge.

---

## Order of operations (recommended)

1. **HTTPS Listener** first — get `raw_telemetry` rows visible from the curl smoke test. This is the highest-risk piece (network egress, auth, dataset write).
2. **Edge process** next — point it at the listener URL with the shared secret. Run `python -m victus_edge.main`. Confirm Position events land in `raw_telemetry` every 5 s.
3. **TS v2 function** — get a successful curl response, then point the edge `FOUNDRY_FUNCTIONS_URL` at it.
4. **Workshop module** — wire the action button. Click it. Observe a row in `commands_seed` (refresh in Dataset preview) and the edge logs.
5. **Verify the round trip** — the edge should print the command (verb, message_id) on stdout; the Workshop command list shows the row.

---

## Phase 1.1 work (after round-trip is closed)

- Transform `telemetry_normalized.py` to parse envelopes from `raw_telemetry` and split by event type.
- Transform `drone_state.py` (replaces the seed) and `commands_log.py` (drives status from telemetry events).
- Function-backed action `issueCommand` (TS v2) that fans out to multiple drones via `deviceIds[]`.
- Additional object types: `videoFrame`, `textMessage`, `mission`. See [foundry/ontology/README.md](ontology/README.md).
- Edge `auth.py` OAUTH mode and `buffer.py` offline buffer.
