# VICTUS BFF — backend-for-frontend

Tiny Express server. Owns the Foundry token (env var, never touches the browser). Fronts a stable REST surface for the [UI](../ui/) so the UI stays Foundry-agnostic.

**Status: live against real Foundry.** All Phase 1–3 endpoints proven end-to-end.

## Why it exists

Browser-direct calls to Foundry hit CORS. Putting the Foundry token in `localStorage` leaks it. A Vite dev proxy works in `npm run dev` but dies in `npm run build && vite preview`. The BFF kills all three problems in ~250 LOC:

- CORS allowlist controlled by `ALLOWED_ORIGIN` env var
- Foundry bearer token only ever in `process.env.FOUNDRY_TOKEN` — server-side
- Same `/api/*` paths in dev and prod; the UI doesn't care which target serves them

## Quick start

```bash
cp .env.example .env       # set FOUNDRY_TOKEN, MOCK_MODE=false
npm install
npm run dev                # tsx watch on src/index.ts; http://localhost:8787
```

Smoke test: `curl http://localhost:8787/api/health` → `{"reachable":true,"token_valid_until_iso":"…","seconds_remaining":…}` against real Foundry.

## Endpoints

| Method | Path | Purpose | Status |
|---|---|---|---|
| GET | `/api/health` | Foundry reachability + token expiry from JWT `exp` claim | live |
| GET | `/api/drones` | Search Objects on `drone` | live (returns 3 seed drones) |
| GET | `/api/commands?deviceId=…&limit=…` | Search Objects on `command` filtered by `deviceId`, sorted by `issuedAt` desc | live |
| POST | `/api/issue-command` | Body `{device_ids[], verb, params_json, priority, expires_in_sec}` — N fan-out via `Promise.allSettled` against `issue-command` action | live |
| GET | `/api/missions` | Search Objects on `mission`, sorted by `createdAt` desc | live |
| POST | `/api/missions` | Body `{name, description, system_prompt, objectives?, target_specs?, area_geo_json?, priority?, roe_profile?}` — generates `mission_id` UUID + timestamps, calls `create-mission` action; 8KB cap on `system_prompt` | live |
| POST | `/api/assign-mission` | Body `{mission_id, device_ids[], expires_in_sec?}` — fetches the mission, builds a clean params payload (drops `"none"` sentinels), fans out N `issue-command` calls with `verb=ASSIGN_MISSION`, embeds `system_prompt` + name + optional structure in `params_json` | live |
| GET | `/api/telemetry?deviceId=…` | Bundles last_position + last_reasoning + last_frame from Phase 4 ontology objects | **pending Phase 4** |

## Source layout

```
bff/src/
├── index.ts        # Express bootstrap + all 7 route handlers
├── foundry.ts      # searchObjects() / applyAction() / pingFoundry() / decodeTokenExpiry()
├── camelcase.ts    # snake↔camel maps for drone, command, mission (matches foundry/README.md table)
└── types.ts        # wire types between BFF and UI; snake_case to match the protocol envelope
```

## Env vars

| Var | Purpose |
|---|---|
| `BFF_PORT` | Default `8787` |
| `ALLOWED_ORIGIN` | CORS allow-origin; default `http://localhost:5173` |
| `FOUNDRY_STACK_URL` | e.g. `https://victus.usw-23.palantirfoundry.com` |
| `FOUNDRY_ONTOLOGY` | API name OR RID of the ontology |
| `FOUNDRY_TOKEN` | Personal API token; required scopes `api:streams-write`, `api:ontologies-read`, `api:ontologies-write` |
| `MOCK_MODE` | `true` returns hardcoded fixtures; `false` hits real Foundry |

## What's NOT in here

- The Foundry token never leaves this process. The UI gets data, never credentials.
- No streaming dataset pushes — the BFF is read-only against `raw_telemetry`. Telemetry inbound is the edge's job, not the operator's.
