# Phase 4c — LLM Reasoning Trace + Video Frame Handoff

This document is a complete handoff for integrating the on-board LLM's reasoning output and video frame thumbnails into the operator dashboard. Everything up to this point (API bridge, command palette, mission editor, live drone state, command ACK status) is already live. This phase plugs the two remaining UI placeholders.

## Current state of the UI

Both placeholders already exist in [`ui/src/components/drones/DroneCard.tsx`](../ui/src/components/drones/DroneCard.tsx):

```tsx
{/* LLM trace placeholder */}
<div className="border-t border-gray-800 pt-2">
  <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1">LLM Reasoning</div>
  <div className="text-xs text-gray-600 italic">awaiting Phase 4 transform · last_reasoning</div>
</div>
```

```tsx
{/* video placeholder */}
<div className="relative bg-black/60 rounded border border-gray-800 aspect-video flex items-center justify-center">
  <div className="text-[11px] text-gray-600 font-mono">
    NO VIDEO · awaiting Phase 2 vision pipeline
  </div>
</div>
```

---

## Wire protocol — what the edge must emit

Both events are already in the protocol schema at [`shared/protocol/schemas/telemetry.schema.json`](../shared/protocol/schemas/telemetry.schema.json) and `docs/PROTOCOL.md`. The edge emits them as standard telemetry envelopes via `publishRecords` to `raw_telemetry`.

### `ReasoningTrace` event

```json
{
  "protocol_version": "0.3.0",
  "message_id": "<uuid>",
  "issued_at": "2026-05-03T02:00:00Z",
  "sender": "drone-uav-01",
  "kind": "telemetry",
  "payload": {
    "event": "ReasoningTrace",
    "command_id": "<uuid of the command being reasoned about>",
    "decision": "SEARCH the harbor perimeter",
    "rationale": "Detected 2 vessels near the eastern dock. Initiating parallel sweep at 150ft AGL to confirm vessel type and heading."
  }
}
```

**Important constraints:**
- `rationale` is capped at 500 characters per protocol.
- `command_id` links the trace to a specific operator command.
- `sender` is `drone-<drone_id>` (e.g. `drone-uav-01`).

### `FrameThumbnail` event

```json
{
  "protocol_version": "0.3.0",
  "message_id": "<uuid>",
  "issued_at": "2026-05-03T02:00:00Z",
  "sender": "drone-uav-01",
  "kind": "telemetry",
  "payload": {
    "event": "FrameThumbnail",
    "format": "jpeg",
    "width": 320,
    "height": 180,
    "b64": "<base64-encoded jpeg, ≤600KB>"
  }
}
```

**Important constraints:**
- Keep the thumbnail small — 320×180 JPEG at quality 60 is ~15-30KB.
- `b64` is a raw base64 string (no `data:image/jpeg;base64,` prefix — that's added by the UI).
- Emit at a low cadence: every 5-10 seconds is plenty.

---

## Transforms needed (victus-transforms repo)

The transforms repo is at `ri.stemma.main.repository.1f853d94-edfa-43c2-bf15-d019deb842b9` and has been cloned to `foundry-transforms/` in this repo. Both transforms follow the **exact same pattern** as `drone_state_live.py`:

- Read `raw_telemetry` (RID `ri.foundry.main.dataset.ed8731a7-4d5c-4741-96bb-fcc2f09608cf`)
- Filter by event type
- Window-deduplicate to **latest row per `sender`** (= latest per drone)
- Strip `drone-` prefix from sender to get `drone_id`
- Write SNAPSHOT to a new dataset

### Transform 1: `last_reasoning.py`

**Output path:** `/Victus-743ed7/phantomORCHESTRATION-hackathon/orchestration-data/last_reasoning_v1`

**Output schema (all STRING except the DOUBLE fields):**

| Column | Type | Notes |
|---|---|---|
| `drone_id` | STRING | PK — sender with `drone-` stripped |
| `command_id` | STRING | UUID of the command being traced |
| `decision` | STRING | Short action string |
| `rationale` | STRING (long-text) | ≤500 chars, the LLM's reasoning |
| `observed_at` | STRING | `issued_at` of the trace envelope |

**Dedup:** `ROW_NUMBER() OVER (PARTITION BY drone_id ORDER BY observed_at DESC) = 1`

### Transform 2: `last_frame.py`

**Output path:** `/Victus-743ed7/phantomORCHESTRATION-hackathon/orchestration-data/last_frame_v1`

**Output schema:**

| Column | Type | Notes |
|---|---|---|
| `drone_id` | STRING | PK |
| `format` | STRING | always `jpeg` |
| `width` | INTEGER | |
| `height` | INTEGER | |
| `b64` | STRING (long-text) | raw base64 JPEG |
| `captured_at` | STRING | `issued_at` of the frame envelope |

**Dedup:** same `ROW_NUMBER()` pattern.

**After writing each transform:**
1. `git add`, `git commit`, `git push` in `foundry-transforms/`
2. Wait for Foundry CI (~2 min)
3. Trigger a dataset build via `mcp__palantir-mcp__build_datasets` with the file path
4. Add input-triggered schedule on `raw_telemetry` (same as `drone_state_v3` and `command_acks_v2`)

---

## Ontology objects needed

Two new object types, each on a fresh global branch → proposal → merge. Follow the same flow as the `mission` and `command_ack` objects.

**Ontology:** `ri.ontology.main.ontology.10d8565f-992c-4cd2-8df5-0328b5d7e46b`  
**Project folder:** `ri.compass.main.folder.e5c96633-8b74-4268-bd42-f4d0d2e3ca53`  
**Namespace:** `ri.compass.main.folder.1b5350a4-4ac5-4803-9c21-1c8096941798`

### `last_reasoning` object type

- `objectTypeId`: `last-reasoning` (Foundry will prepend namespace → `pzqmccug.last-reasoning`)
- `apiName`: `lastReasoning`
- `primaryKey`: `drone_id`
- `titlePropertyTypeId`: `drone_id`
- All properties STRING non-nullable; `rationale` should have `isLongText: true`

### `last_frame` object type

- `objectTypeId`: `last-frame`
- `apiName`: `lastFrame`
- `primaryKey`: `drone_id`
- `titlePropertyTypeId`: `drone_id`
- `b64` should have `isLongText: true`, `indexedForSearch: false` (it's binary data, not searchable)

---

## BFF changes needed

### New types in `bff/src/types.ts`

```typescript
export type LastReasoning = {
  drone_id: string;
  command_id: string;
  decision: string;
  rationale: string;
  observed_at: string;
};

export type LastFrame = {
  drone_id: string;
  format: string;
  width: number;
  height: number;
  b64: string;
  captured_at: string;
};
```

### New camelCase translators in `bff/src/camelcase.ts`

Foundry will auto-camelCase `observed_at → observedAt`, `captured_at → capturedAt`, `command_id → commandId`, `drone_id → droneId`.

```typescript
const LAST_REASONING_C2S = {
  droneId: "drone_id", commandId: "command_id",
  decision: "decision", rationale: "rationale", observedAt: "observed_at",
};

const LAST_FRAME_C2S = {
  droneId: "drone_id", format: "format",
  width: "width", height: "height",
  b64: "b64", capturedAt: "captured_at",
};
```

### New BFF route: `GET /api/telemetry?deviceId=`

Returns a bundle of `{ last_reasoning: LastReasoning | null, last_frame: LastFrame | null }` for the given drone. Queries both `lastReasoning` and `lastFrame` object types via `searchObjects`. Fails gracefully (returns nulls) if either object type doesn't exist yet.

```typescript
app.get("/api/telemetry", async (req, res) => {
  const deviceId = String(req.query.deviceId ?? "");
  const [reasoningObjs, frameObjs] = await Promise.all([
    searchObjects(FOUNDRY, "lastReasoning", {
      where: { type: "eq", field: "droneId", value: deviceId },
      pageSize: 1,
    }).catch(() => []),
    searchObjects(FOUNDRY, "lastFrame", {
      where: { type: "eq", field: "droneId", value: deviceId },
      pageSize: 1,
    }).catch(() => []),
  ]);
  res.json({
    last_reasoning: reasoningObjs[0] ? lastReasoningFromFoundry(reasoningObjs[0]) : null,
    last_frame: frameObjs[0] ? lastFrameFromFoundry(frameObjs[0]) : null,
  });
});
```

---

## UI changes needed

### `ui/src/api/types.ts` — add types

```typescript
export type LastReasoning = {
  drone_id: string;
  command_id: string;
  decision: string;
  rationale: string;
  observed_at: string;
};

export type LastFrame = {
  drone_id: string;
  format: string;
  width: number;
  height: number;
  b64: string;
  captured_at: string;
};
```

### `ui/src/api/client.ts` — add telemetry call

```typescript
telemetry: (deviceId: string, signal?: AbortSignal) =>
  jget<{ last_reasoning: LastReasoning | null; last_frame: LastFrame | null }>(
    `/api/telemetry?deviceId=${encodeURIComponent(deviceId)}`, signal
  ),
```

### `ui/src/components/drones/DroneCard.tsx` — add a polling hook + replace placeholders

Add a `useTelemetry(droneId)` hook polling every 10s (slower than commands — reasoning doesn't change that often). Replace the two placeholder divs:

**LLM Reasoning → `LLMTracePanel`:**
```tsx
{reasoning ? (
  <div className="space-y-1">
    <div className="text-xs font-medium text-gray-200">{reasoning.decision}</div>
    <div className="text-[11px] text-gray-400 leading-snug">{reasoning.rationale}</div>
    <div className="text-[10px] text-gray-600 font-mono">{timeAgo(reasoning.observed_at)}</div>
  </div>
) : (
  <div className="text-xs text-gray-600 italic">no reasoning yet</div>
)}
```

**Video → `VideoPanel`:**
```tsx
{frame?.b64 ? (
  <img
    src={`data:image/jpeg;base64,${frame.b64}`}
    alt={`${drone.callsign} camera`}
    className="w-full rounded object-cover"
  />
) : (
  <div className="text-[11px] text-gray-600 font-mono">NO VIDEO</div>
)}
```

---

## End-to-end latency expectation

Same pipeline as `drone_state_v3` and `command_acks_v2`:

| Step | Latency |
|---|---|
| LLM emits `ReasoningTrace` / `FrameThumbnail` → `raw_telemetry` hot buffer | instant |
| Foundry flushes hot buffer to cold | ~5-15 min |
| Input-triggered build of `last_reasoning_v1` / `last_frame_v1` | ~1-2 min |
| UI polls `/api/telemetry` every 10s | ≤10s |
| **Worst case end-to-end** | **~17 min** |

This is acceptable for operator awareness. The operator already knows what command was issued; the reasoning trace is a post-hoc confirmation, not real-time guidance.

---

## Quick checklist for the LLM project

- [ ] Edge emits `ReasoningTrace` events (at LLM decision points) and `FrameThumbnail` events (every ~10s)
- [ ] `last_reasoning.py` transform written + pushed + built + scheduled
- [ ] `last_frame.py` transform written + pushed + built + scheduled  
- [ ] `last_reasoning` ontology object created + proposal merged
- [ ] `last_frame` ontology object created + proposal merged
- [ ] BFF `GET /api/telemetry` endpoint added
- [ ] UI `LLMTracePanel` and `VideoPanel` placeholders replaced with live components
- [ ] Smoke test: issue a SEARCH command → edge reasons → trace appears in DroneCard within ~17 min
