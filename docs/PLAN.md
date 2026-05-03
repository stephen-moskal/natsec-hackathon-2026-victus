# Hackathon Plan

## Where we are right now (snapshot)

| Demo criterion | Status | Notes |
|---|---|---|
| 1. **Loop closed** — operator click → edge → ACK visible | ✅ done | Round-trip ~1s. Operator surface is the React UI in [`ui/`](../ui/) (and direct curl), not Workshop. Foundry-side command status flip PENDING→ACKED still pending the Phase 4 streaming transform; until then the UI shows the ACK on the edge log but the `command.status` field stays PENDING. |
| 2. **Reasoning visible** — live LLM reasoning + detections | ⏳ partial | Telemetry pipe exists for `ReasoningTrace` and `Detection` envelopes; UI placeholders are in `LLMTracePanel` / `VideoPanel` waiting on Phase 4 `last_reasoning` and `last_frame` ontology objects + transforms. The on-board LLM is itself stubbed (`mock` reasoner) — wiring Gemma 3 / Qwen2.5-VL is Phase 4+. |
| 3. **Multi-drone** — N drones commanded independently from one view | ✅ done (orchestration side) | Command palette multi-selects drones and fans out via `Promise.allSettled`. Mission editor assigns one mission to N drones in a single action. Limit today is that only one Jetson is running an actual edge process — the other rows are seed data. |
| 4. **Survives link drop** — scripted outage + clean recovery | ❌ not yet | Edge has the buffer hook (`drain_buffer()` placeholder) but persistence to disk is Phase 1.1 in the original sequencing. |

The implementation phases below describe the **original** strategy. The numbering since then has drifted because we replaced "Workshop dashboard" with a React UI + BFF, and split that work across our internal Phases 0–3. See the root [README.md](../README.md) for the current state.

## Phases

### Phase 0 — Scaffolding (this commit)
- Repo structure, protocol schemas, module stubs, READMEs.
- Decide on Foundry project location and ontology namespace.

### Phase 1 — API loop, no AI (priority)
- Foundry: REST API data source with a webhook for telemetry ingestion. Streaming dataset → ontology. `issueCommand` TypeScript function. Minimal Workshop with one button per verb and a telemetry table.
- Edge: `comms.foundry_client` posts heartbeats and polls for commands. `protocol` validates against schemas. `main` keeps an in-memory intent and ACKs commands. No vision, no LLM, no autonomy.
- **Exit criterion:** A command sent from Workshop appears in the edge process logs within 5 s, and a `CommandAck` is visible in Workshop within 5 s after that.

### Phase 2 — Vision + reasoning on the edge
- Edge: `vision.pipeline` reads from a webcam or file (Orin GStreamer pipeline a stretch goal), runs a stock detector (YOLOv8n or similar). `llm.reasoner` runs Gemma 3 4B IT or Qwen2.5-VL-7B locally via `llama.cpp` server. Reasoner ingests (intent, latest detections, frame) and emits `ReasoningTrace` + chosen action.
- Foundry: persist `ReasoningTrace` and `Detection` events into ontology. Workshop shows the reasoning feed and last detection per drone.
- **Exit criterion:** A SCAN command yields detections + reasoning traces visible in Workshop within 10 s of issuance.

### Phase 3 — Multi-drone orchestration
- Spin up 2–3 edge processes with distinct `drone_id`s on a single laptop (or one Orin + two laptops).
- Workshop dashboard shows them on a map with per-drone panels.
- Operator can issue distinct commands to each.
- **Exit criterion:** Three drones execute three different verbs concurrently, each with their own visible reasoning feed.

### Phase 4 — Link-loss resilience
- Edge `foundry_client` writes telemetry to a local SQLite/JSONL buffer when POST fails. Drains in order on reconnect.
- Edge enforces command expiry → `HOLD` fallback.
- Demo script: pull the network cable for 30 s mid-mission, show graceful fallback and clean recovery.
- **Exit criterion:** During a 30 s comms outage, the drone keeps executing its last unexpired intent, then holds; on reconnect, no telemetry is lost.

### Phase 5 — Polish (only if time allows)
- Real MAVLink + SITL (PX4 or ArduPilot Gazebo) so the simulated drone actually moves.
- Frame thumbnails inline in Workshop.
- ROE profiles wired through the function layer.

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Foundry REST API ingestion is unfamiliar; first wiring takes longer than expected. | Start Phase 1 immediately. Use the simplest possible payload (single field) end-to-end before adding the real schema. |
| LLM inference too slow on Orin to keep up with video. | Decouple vision tick rate from reasoner tick rate. Reasoner runs on detections, not frames. Fall back to text-only Gemma 3 1B if needed. |
| Workshop map widget is fiddly. | Have a table-only fallback view ready. Map is great if it works, not blocking otherwise. |
| Multi-drone state collision in ontology. | Primary key on `drone_id`; all events scoped by `drone_id`. Reviewed before Phase 3. |
| Link-loss demo flakes live. | Pre-record a backup video of the resilience scenario. Live attempt first, video if it fails. |

## Team split (suggested)

- **Foundry lead** — REST data source, ontology, transforms, functions, Workshop layout.
- **Edge lead** — Python package, comms client, vision pipeline, LLM wrapper.
- **Protocol/integration** — owns the schemas, writes the integration test that proves Phase 1 exit criterion, owns the demo script.

One person can own protocol while contributing to either side; the role is small but central.

## Demo script (target ~4 min)

1. (30 s) Show the kit: Orin + battery + radio. Show Workshop dashboard with three drones nominal.
2. (60 s) Issue a SCAN to drone 1. Watch the detection and reasoning feed populate. Click a detection — issue INVESTIGATE.
3. (60 s) Issue different commands to drones 2 and 3 in parallel. Show all three reasoning feeds advancing independently.
4. (60 s) Pull the network cable on drone 1. Show the dashboard mark it `LINK_LOST` while drone 1 continues its task. Reconnect. Show telemetry catch-up.
5. (30 s) Why this matters — intent at the edge, doctrine-shaped commands, no cloud dependency.
