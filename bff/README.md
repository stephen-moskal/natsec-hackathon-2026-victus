# VICTUS BFF — backend-for-frontend

Tiny Express server. Owns the Foundry token (env var, never touches the browser). Fronts a stable REST surface for the [UI](../ui/) so the UI stays Foundry-agnostic.

## Why it exists

Browser-direct calls to Foundry hit CORS. Putting the Foundry token in `localStorage` leaks it. A Vite dev proxy works in `npm run dev` but dies in `npm run build && vite preview`. The BFF kills all three problems with ~150 LOC:

- CORS allowlist controlled by `ALLOWED_ORIGIN` env var
- Foundry bearer token only ever in `process.env.FOUNDRY_TOKEN` — server-side
- Same `/api/*` paths in dev and prod; the UI doesn't care which target serves them

## Quick start

```bash
cp .env.example .env       # MOCK_MODE=true is fine for Phase 0
npm install
npm run dev                # tsx watch on src/index.ts; http://localhost:8787
```

Smoke test: `curl http://localhost:8787/api/health` → `{"reachable":false,...}` in mock mode.

## Endpoints

| Method | Path | Purpose | Phase |
|---|---|---|---|
| GET | `/api/health` | Foundry reachability + token expiry from JWT `exp` claim | Phase 0 (mock) → Phase 1 (real) |
| GET | `/api/drones` | Search Objects on `drone` | Phase 0 (mock) → Phase 1 (real) |
| GET | `/api/commands?deviceId=…&limit=…` | Search Objects on `command` filtered by deviceId | Phase 0 (empty) → Phase 2 (real) |
| GET | `/api/missions` | Search Objects on `mission` | Phase 0 (empty) → Phase 3 (real) |
| POST | `/api/issue-command` | Body `{device_ids[], verb, params_json, priority, expires_in_sec}` — fan-out via `Promise.allSettled` | Phase 0 (mock OK) → Phase 2 (real) |
| POST | `/api/missions` | Create a Mission via `create-mission` action | Phase 3 |
| POST | `/api/assign-mission` | Body `{mission_id, device_ids[]}` — issues N ASSIGN_MISSION commands | Phase 3 |
| GET | `/api/telemetry?deviceId=…` | Bundles last_position + last_reasoning + last_frame from Phase 4 ontology objects | Phase 4 |

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
