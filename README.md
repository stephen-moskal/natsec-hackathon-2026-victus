# VICTUS — Mission-Aware Edge-Based Reasoning

NatSec Hackathon 2026 entry. Track: **Tactical Edge Autonomy**.

## One-line pitch

A single operator commands a swarm of autonomous drones from a backpack-portable edge kit. Each drone runs a small reasoning LLM on an NVIDIA Jetson Orin, ingests its own video, and acts on terse, doctrine-shaped commands sent from a Palantir Foundry orchestrator — even when the link is intermittent.

## Why this matters

Operators in austere environments cannot rely on cloud inference, full-motion video back to a TOC, or low-latency control loops. Today's autonomy is brittle to link loss and command-heavy. We push *intent* to the edge — short, structured commands in a shared military vocabulary — and let an on-board LLM resolve that intent into action against what the drone is actually seeing.

## System at a glance

```
+----------------------------+         +-----------------------------+
|  Operator (Foundry)        |         |  Drone (Jetson Orin)        |
|                            |  cmd    |                             |
|  Workshop dashboard        | ------> |  Reasoner (Gemma 3 / Qwen)  |
|  Orchestrator function     |         |  Vision pipeline            |
|  Ontology (Drone, Mission, | <------ |  Autonomy controller        |
|  Command, Observation)     |  tlm    |  Foundry comms client       |
+----------------------------+         +-----------------------------+
            ^                                       |
            |       structured JSON over HTTPS      |
            +------- (commands + telemetry) --------+
                           video frames
                          + reasoning text
```

The two sides speak a shared, versioned protocol — see [docs/PROTOCOL.md](docs/PROTOCOL.md) — defined once in [shared/protocol/schemas/](shared/protocol/schemas/) and consumed by both the Foundry function layer and the edge client.

## Repo layout

```
.
├── docs/                   # Architecture, protocol, hackathon plan
├── foundry/                # Foundry-side code (transforms, functions, ontology, workshop)
├── edge/                   # NVIDIA Orin Python package
└── shared/                 # Protocol schemas shared by both sides
```

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — full system architecture
- [docs/PROTOCOL.md](docs/PROTOCOL.md) — command/telemetry dictionary
- [docs/PLAN.md](docs/PLAN.md) — hackathon phasing and success criteria
- [foundry/README.md](foundry/README.md) — Foundry-side overview
- [edge/README.md](edge/README.md) — edge-side overview

## Hackathon scope

The first deliverable is **the API layer** — bidirectional message passing between Foundry and a simulated edge node, with the protocol schemas locked in. Vision, LLM, and real flight control come after the loop is closed.

See [docs/PLAN.md](docs/PLAN.md) for the phased roadmap.
