# Shared protocol

JSON Schemas that define the contract between Foundry and the edge. Both sides import these at build time and validate every message they send or receive.

See [docs/PROTOCOL.md](../../docs/PROTOCOL.md) for the human-readable spec.

## Files

- [schemas/envelope.schema.json](schemas/envelope.schema.json) — outer envelope structure (every message)
- [schemas/command.schema.json](schemas/command.schema.json) — `kind=command` payloads (verbs, params)
- [schemas/telemetry.schema.json](schemas/telemetry.schema.json) — `kind=telemetry` payloads (event types)

## Versioning

The `$id` of each schema includes the protocol semver. A breaking change bumps the major and both sides must redeploy together. Adding an optional field is a minor; adding a new verb or event type is a minor; removing or retyping a field is a major.

## Consumers

- **Edge:** `victus_edge.comms.protocol` validates with `jsonschema`.
- **Foundry functions:** TypeScript build copies the schemas into `dist/schemas/` and validates with `ajv`.
- **Foundry transforms:** `telemetry_normalized.py` parses inbound JSON; schema validation is performed at the function/webhook layer, so transforms can assume well-formed input.
