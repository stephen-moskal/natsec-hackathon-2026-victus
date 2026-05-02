# Edge — VICTUS edge node

Python package that runs on the NVIDIA Jetson Orin (or a laptop simulating one). Owns the on-board reasoning loop and the Foundry interface.

## Layout

```
edge/
├── pyproject.toml
├── src/victus_edge/
│   ├── main.py             # event loop, owns the intent state
│   ├── config.py           # env-based config
│   ├── comms/
│   │   ├── foundry_client.py   # POST telemetry, poll commands, buffer when offline
│   │   └── protocol.py         # envelope encode/decode + schema validation
│   ├── llm/
│   │   └── reasoner.py     # wraps Gemma 3 / Qwen2.5-VL via llama.cpp / vLLM
│   ├── vision/
│   │   └── pipeline.py     # capture + detector
│   ├── autonomy/
│   │   └── controller.py   # MAVLink translation (SITL stub for hackathon)
│   └── telemetry/
│       └── streamer.py     # batched outbound queue
└── tests/
```

## Runtime model

Single process, asyncio event loop. Modules communicate by passing typed messages through asyncio queues:

```
   vision.pipeline ──► (Detection, Frame) ──┐
                                            ▼
   foundry_client  ──► (Command)       ──► main ──► reasoner ──► (Action, ReasoningTrace)
                                            │                          │
   command state  ◄────────────────────────┘                          ▼
                                                              autonomy.controller
                                                                      │
                                                                      ▼
                                                                MAVLink / SITL
   ▲ telemetry.streamer drains all outbound events to foundry_client
```

The reasoner only runs when there is a current intent and either (a) a new detection has arrived, or (b) a tick timeout has elapsed. This decouples LLM throughput from camera frame rate.

## Configuration

All config via environment variables, read once in `config.py`:

| Var | Purpose |
|---|---|
| `VICTUS_DRONE_ID` | This node's identity. Required. |
| `VICTUS_FOUNDRY_BASE_URL` | Foundry REST API data source URL. |
| `VICTUS_FOUNDRY_TOKEN` | Bearer token for the data source. |
| `VICTUS_LLM_BACKEND` | `llama_cpp_server` \| `vllm` \| `mock`. Default `mock` in dev. |
| `VICTUS_LLM_MODEL_PATH` | Path or URL to the model. |
| `VICTUS_VISION_SOURCE` | `webcam:0` \| `file:/path/to.mp4` \| `gst:<pipeline>`. Default `mock`. |
| `VICTUS_AUTONOMY_BACKEND` | `sitl` \| `mock`. Default `mock`. |
| `VICTUS_TELEMETRY_BUFFER_PATH` | Path for offline buffer. Default `./runtime/buffer.jsonl`. |
| `VICTUS_LOG_LEVEL` | Default `INFO`. |

## Dev quickstart (planned)

```bash
cd edge
python -m venv .venv && source .venv/bin/activate
pip install -e .

export VICTUS_DRONE_ID=uav-01
export VICTUS_FOUNDRY_BASE_URL=...
export VICTUS_FOUNDRY_TOKEN=...
# all backends default to "mock" so this runs without a model or camera
python -m victus_edge.main
```

## Module status

All modules are currently stubs with interfaces only. Implementation lands in Phase 1 (`comms`, `protocol`, `main`) and Phase 2 (`vision`, `llm`, `autonomy`).
