# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project: VICTUS

NatSec Hackathon 2026 entry — Tactical Edge Autonomy. A Palantir Foundry operator console commands simulated drones; each drone runs an asyncio loop on an NVIDIA Jetson Orin that polls Foundry for commands and posts telemetry back. Vision + on-board LLM reasoning come in Phase 2; Phase 1 just closes the bidirectional API loop.

Three top-level units, deployed independently but built around one shared contract:

```
edge/      Python 3.10+ package run on Jetson Orin (or laptop sim)
foundry/   PySpark transforms, TypeScript functions, ontology, Workshop module
shared/    JSON Schemas — the protocol contract
```

The phased hackathon roadmap (Phase 0 → Phase 4) lives in `docs/PLAN.md`. Most modules in `edge/src/victus_edge/` are stubs that get filled in by phase. Read `docs/ARCHITECTURE.md` and `docs/PROTOCOL.md` first when picking up unfamiliar work.

## Commands

### Edge (Python)

```bash
cd edge
python -m venv .venv && source .venv/bin/activate
pip install -e .                  # core only
pip install -e .[dev]             # adds pytest, pytest-asyncio, ruff
pip install -e .[vision,llm,autonomy]   # Phase 2 backends

# Run the edge process (all backends default to "mock", but Foundry env vars are required)
python -m victus_edge.main        # or: victus-edge

# Tests (pytest-asyncio configured via pyproject)
cd edge && pytest                 # all tests
pytest tests/test_protocol.py     # single file
pytest tests/test_protocol.py::test_validate_rejects_unknown_verb   # single test

# Lint
ruff check edge/
```

`.env.example` at repo root lists every required edge env var. Copy to `.env` and fill in `FOUNDRY_LISTENER_URL`, `FOUNDRY_FUNCTIONS_URL`, and `FOUNDRY_TOKEN` before running.

### Foundry side

No buildable Foundry code is committed yet — `foundry/transforms-python/`, `foundry/functions/`, `foundry/ontology/`, and `foundry/workshop/` currently hold design notes only. Actual transforms/functions are authored inside Foundry Code Repositories on the `phantom-orchestration-phase1` branch (see `foundry/README.md` for RIDs and `foundry/WORKSHOP_RUNBOOK.md` for the UI-side bring-up steps).

## Architecture

### The protocol is the contract

`shared/protocol/schemas/` holds three JSON Schemas (envelope + command + telemetry). Both stacks validate every message they send and receive against these schemas:

- **Edge:** `victus_edge.comms.protocol` uses `jsonschema` (Draft 2020-12). `_REPO_ROOT` resolves via `Path(__file__).resolve().parents[4]` — moving the package outside this repo layout will break schema loading.
- **Foundry functions:** TypeScript build copies schemas to `dist/schemas/` and validates with `ajv` before any ontology write.

`protocol.PROTOCOL_VERSION` (currently `0.2.0`) and `PROTOCOL_MAJOR` (`0`) are tightly coupled. `validate()` rejects any envelope whose major doesn't match — so bumping the major requires both sides redeployed in lockstep. The `0.2.0` bump added the `ASSIGN_MISSION` verb.

### Edge event loop

`victus_edge/main.py` wires two concurrent asyncio tasks that share one `FoundryClient`:

- `_command_poller` — polls the `pollCommands` query function every `COMMAND_POLL_INTERVAL_S`, ACKs each new command immediately with `result=ACCEPTED`, advances a cursor by `message_id`. Phase 2 plugs the reasoner in at the same dispatch point.
- `_telemetry_emitter` — emits a `Position` heartbeat every `POSITION_EMIT_INTERVAL_S` (currently mocked coordinates).

Modules under `vision/`, `llm/`, `autonomy/`, and `telemetry/` are scaffolded with interface-only stubs. Don't wire them into `main.py` until their phase — see `docs/PLAN.md`.

`config.py` is the only place env is read; every module takes a `Config` instance so tests can substitute fixtures. `auth.TokenProvider` hides STATIC vs OAUTH behind a single `await provider.token()` coroutine; OAuth refresh is guarded by an `asyncio.Lock` to prevent token-fetch storms under 401s.

`comms/foundry_client.py` posts telemetry **one envelope per request** (Foundry HTTPS Listener has a 1 MB per-request cap). Retry policy: exponential backoff via `tenacity`, 3 attempts, only on transport errors and 5xx. 4xx errors are logged and dropped — no buffering. Phase 1.1 is where the JSONL offline buffer (`drain_buffer`) actually gets implemented; the method exists as a no-op stub today.

### Foundry-side design (not yet code)

Five ontology object types (`drone`, `command`, `videoFrame`, `textMessage`, `mission`) backed by streaming/batch datasets. Two object types are *latest-row-per-device* projections (`drone`, `videoFrame`) — primary key is `drone_id`, not `message_id`.

**Command lifecycle is asymmetric**: the `issueCommand` action writes a row with `status=PENDING`, but the `pollCommands` query function and the action *never write back* to status. The status enum (`PENDING → ACKED → COMPLETED`, plus `EXPIRED`/`REJECTED`/`ABORTED`) is driven entirely by telemetry events the edge emits (`CommandAck`, `MissionEvent`). The `commands_log.py` transform (Phase 1.1) joins issued commands with telemetry to compute `status`, `acked_at`, `completed_at`. A separate `commands_expire.py` scheduled batch flips stuck-PENDING rows past `expires_at` to `EXPIRED`.

The `pollCommands` query function is what the edge calls every 2 s; its endpoint shape (`POST {functionsBaseUrl}/pollCommands/execute`, body `{parameters: {droneId, sinceMessageId}}`, response wrapped in `{value: {commands, cursor}}`) is mirrored by `FoundryClient.poll_commands` — keep them in sync.

All ontology resources currently live on the `phantom-orchestration-phase1` global branch and are not visible on `main` until merged via a Foundry proposal. Specific RIDs (stack URL, namespace folder, ontology, datasets, object types, action type) are recorded in `foundry/README.md`.

### Backends are pluggable, default to mock

LLM (`llama_cpp_server` / `vllm` / `mock`), vision (`webcam:N` / `file:...` / `gst:...` / `mock`), autonomy (`sitl` / `mock`) — all selected by env var, default `mock`. This is intentional: the edge process is meant to start cleanly on a laptop with nothing more than the Foundry env vars. Don't add hard dependencies on heavy backends to the core path.

LLM Dockerfiles for Jetson live at `edge/src/victus_edge/llm/model_containers/` (`gemma4.Dockerfile`, `qwen3vl.Dockerfile`, `llama_base.Dockerfile`). These build container images for `llama-server` deployments — the Python process just drives the video pipeline and posts to `localhost:8080`.

## Conventions worth knowing

- **Timestamps:** ISO 8601 UTC with `Z` suffix (`2026-05-02T18:00:00Z`). `protocol._now_iso()` produces this format. Don't use `isoformat()` directly — it emits `+00:00` which the schema's `format: date-time` accepts but downstream tools may not.
- **GeoPoint:** ontology uses `lat,lon` string format (no parens). Workshop map widgets won't render if the property is plain `STRING`.
- **Logging:** `structlog` with key=value rendering. Use `log.info("event_name", key=value, ...)` — the first arg is a snake_case event name, never a free-form sentence.
- **Tests:** `pytest-asyncio` is in dev extras. The protocol test file uses synchronous tests because protocol functions are sync; async tests will appear when `foundry_client` and `main` get covered.
- **Ruff:** line-length 100, target py310. Run before committing.
