# Edge tests

Pytest + pytest-asyncio.

## Planned tests

- **`test_protocol.py`** — round-trip envelopes through `encode → validate → decode`. Reject schema-invalid payloads. Reject mismatched protocol majors.
- **`test_foundry_client_offline.py`** — simulate a connection failure; verify telemetry batches land in the buffer file and drain in order on reconnect.
- **`test_main_intent_state.py`** — verify command expiry triggers the HOLD fallback. Verify `supersedes` semantics. Verify priority preemption.
- **`integration/test_loop_phase1.py`** — spin up the edge against a fake Foundry HTTP server (httpx mock), send a command, assert ACK is observed and intent state updates.

No tests committed yet — added alongside Phase 1 implementation.
