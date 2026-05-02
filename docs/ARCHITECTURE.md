# Architecture

## Design tenets

1. **Intent at the edge.** The operator sends *what* and *why*; the edge resolves *how*. Commands are short, doctrine-shaped strings, not waypoint dumps.
2. **Survive the link.** Every command is idempotent and time-bounded. Every telemetry packet stands alone. A drone that loses comms continues executing its last accepted intent until its expiry, then falls back to a safe behavior.
3. **One protocol, two implementations.** JSON Schemas in [shared/protocol/schemas/](../shared/protocol/schemas/) are the contract. Foundry-side TypeScript and edge-side Python both validate against them.
4. **Foundry is the orchestrator, not the brain.** The dashboard fuses telemetry, lets the operator issue intent, and stores history. It does not steer the aircraft frame-by-frame.

## Components

### Edge (drone) — NVIDIA Jetson Orin

| Module | Responsibility |
|---|---|
| `victus_edge.comms.foundry_client` | Long-poll for new commands; POST telemetry, detections, and reasoning traces back to Foundry. Buffers when offline. |
| `victus_edge.comms.protocol` | Encode/decode/validate messages against the shared schemas. |
| `victus_edge.llm.reasoner` | Wraps a small VLM (Gemma 3 4B IT or Qwen2.5-VL-7B) running locally via `llama.cpp` or `vLLM`. Takes (current intent, recent observations, latest frame) → next action + reasoning text. |
| `victus_edge.vision.pipeline` | GStreamer/NVDEC capture from the onboard camera, sampled at N Hz. Runs a lightweight detector (YOLO-class) and forwards frames + detections to the reasoner. |
| `victus_edge.autonomy.controller` | Translates reasoner output into MAVLink commands for PX4/ArduPilot. Hackathon: simulator (Gazebo / SITL) or stubbed responses. |
| `victus_edge.telemetry.streamer` | Periodic position/health/status emission; opportunistic frame thumbnails + reasoning excerpts. |
| `victus_edge.main` | Event loop. Owns the intent state, applies expiries and fallbacks, dispatches between modules. |

### Foundry (operator side)

| Component | Responsibility |
|---|---|
| **REST API data source + webhook** | Inbound endpoint that the edge POSTs telemetry to. Becomes a streaming dataset. |
| **Transforms (Python)** | Normalize telemetry, derive tracks, persist reasoning traces, build per-drone aggregates. |
| **Ontology** | `Drone`, `Mission`, `Command`, `Observation`, `Detection` object types with link types between them. |
| **Functions (TypeScript)** | `issueCommand(droneId, intent, params, expiry)` action — validates, signs, queues for delivery. `cancelCommand`, `setROE`, etc. |
| **Workshop dashboard** | Map of drones, per-drone video thumbnail + reasoning feed, command palette, mission timeline. |

### Shared

`shared/protocol/schemas/` holds the JSON Schemas. Both sides import them at build time. The schemas are versioned (`"$id"` includes a semver). A breaking change bumps the major version and both sides must be redeployed.

## Message flow

### Command (Foundry → edge)

1. Operator clicks an action in Workshop (e.g. *Investigate POI-7*).
2. Workshop invokes the `issueCommand` Foundry function.
3. The function writes a `Command` ontology object and enqueues delivery.
4. Edge `foundry_client` polls (or holds a long-poll) and pulls the command.
5. Edge validates against `command.schema.json`, ACKs receipt by POSTing a `CommandAck` telemetry event.
6. Reasoner ingests new intent on its next tick.

### Telemetry (edge → Foundry)

1. Edge modules emit events into a local queue: `Position`, `Status`, `Detection`, `ReasoningTrace`, `FrameThumbnail`, `CommandAck`, `MissionEvent`.
2. `comms.foundry_client` batches and POSTs to the Foundry REST endpoint.
3. If offline, the queue persists to disk; on reconnect, batches are flushed in order with original timestamps preserved.
4. Foundry transforms append to streaming datasets and update ontology object properties.

## Why a long-poll instead of WebSocket

Long-poll over plain HTTPS survives more middleboxes, captive portals, and asymmetric tactical links than WebSocket. It is also trivially compatible with Foundry REST API data sources without custom infrastructure. We can swap to WebSocket later if latency demands it.

## Latency budget (target)

| Hop | Budget |
|---|---|
| Operator click → command in flight | < 500 ms |
| Command in flight → edge ACK | < 2 s nominal, < 30 s on poor link |
| Frame → detection → reasoning → action | < 1 s on Orin (target; LLM dominant) |
| Telemetry emit → visible in Workshop | < 3 s |

## What is explicitly out of scope for the hackathon

- Real flight, real RF link, real ROE enforcement.
- Hardened auth (we use a shared bearer token; production would use mTLS + per-drone identity).
- Multi-tenant orchestration. One operator, up to ~3 simulated drones for the demo.
- Model fine-tuning. We use stock weights with prompt engineering only.
