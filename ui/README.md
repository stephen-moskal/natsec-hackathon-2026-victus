# VICTUS UI — Operator Dashboard

React + Vite + TypeScript + Tailwind v4. Talks to the BFF in [`../bff/`](../bff/), never to Foundry directly. Visual conventions match the [phantomsight-annotator](/Users/smoskal/Documents/Foundry/phantomSIGHT-training/phantomsight-annotator) project (dark theme, blue accent, sidebar layout).

**Status: Phases 2 + 3 live against real Foundry.** Operator can monitor the fleet, issue policy commands to N drones, author missions with a system_prompt, and assign them.

## Quick start

```bash
# Terminal 1
cd bff
cp .env.example .env       # set FOUNDRY_TOKEN, MOCK_MODE=false
npm install && npm run dev # http://localhost:8787

# Terminal 2
cd ui
cp .env.example .env       # VITE_BFF_URL=http://localhost:8787
npm install && npm run dev # http://localhost:5173
```

Open `http://localhost:5173`. You should see the VICTUS logo, sidebar (Dashboard / Missions / Settings), and 3 drone cards (ALPHA / BRAVO / CHARLIE) populated from the real `drone` ontology object. Link dots will be **red** until Phase 4's `drone_state_live` transform lands — the seed `last_seen_at` is in the past.

## Routes

| Route | What it does |
|---|---|
| `/` (Dashboard) | Fleet grid (left, 3 `DroneCard`s) + `CommandPalette` (right). Each card shows telemetry, current mission (derived from latest non-rejected `ASSIGN_MISSION`), recent commands, video/LLM placeholders. Polls `/api/drones` every 5s; each card polls `/api/commands?deviceId=…` every 3s (one fetch shared by `CommandList` + `CurrentMissionPanel`). |
| `/missions` | 3-column layout: `MissionEditor` (left) + `MissionList` (middle, radio-select) + `MissionAssignForm` (right). Polls `/api/missions` every 5s. |
| `/settings` | Foundry health + token expiry from JWT `exp` claim. |

## Operator workflows

**Issue a command to N drones (Phase 2):**
1. Dashboard → check the boxes for the target drones in the right-side `DroneMultiSelect`
2. Click a verb chip in `VerbPicker` (10 policy verbs, color-coded)
3. Edit `params_json` (live JSON validation; pre-filled skeleton per verb)
4. Set priority + expires-in
5. **Send** — fan-out via `Promise.allSettled` on the BFF; `SendResultBanner` shows ✓/✗ per drone with a retry-failed button.

**Author + assign a mission (Phase 3):**
1. Missions → fill in **Name** + **System Prompt** (the latter becomes the top of the on-board LLM's system prompt). Optional: description, objectives, target_specs, area_geo_json. **Load example** button pre-fills a working demo.
2. Click **Create Mission** → row appears at the top of the library, auto-selected.
3. Pick drones in `MissionAssignForm`, click **Assign** → BFF looks up the mission, fans out N `ASSIGN_MISSION` commands carrying the mission's `system_prompt` in `params_json`.
4. Within ~3s, the matching `DroneCard`'s **Current Mission** panel reflects the new mission name + truncated prompt with a "show full" toggle.

## Layout

```
ui/src/
├── App.tsx                       # router (Dashboard / Missions / Settings)
├── main.tsx                      # bootstrap
├── index.css                     # Tailwind v4 base + dark scrollbars
├── api/
│   ├── client.ts                 # fetch wrapper hitting /api/*
│   └── types.ts                  # Drone, Command, Mission, Create/Assign request shapes
├── components/
│   ├── layout/{Sidebar,PageHeader}.tsx
│   ├── drones/
│   │   ├── DroneGrid.tsx
│   │   ├── DroneCard.tsx              # owns the per-card 3s command poll
│   │   ├── TelemetryPanel.tsx
│   │   ├── LinkStatusDot.tsx
│   │   ├── CommandList.tsx            # renders shared commands array
│   │   └── CurrentMissionPanel.tsx    # derives mission from latest ASSIGN_MISSION
│   ├── commands/
│   │   ├── CommandPalette.tsx
│   │   ├── DroneMultiSelect.tsx       # reused by MissionAssignForm
│   │   ├── VerbPicker.tsx
│   │   ├── ParamsEditor.tsx
│   │   └── SendResultBanner.tsx       # reused by MissionAssignForm
│   ├── missions/
│   │   ├── MissionEditor.tsx          # form: name, system_prompt (8KB cap), optional structure
│   │   ├── MissionList.tsx            # radio-select with prompt preview
│   │   └── MissionAssignForm.tsx      # mission picker + drone multi-select + Assign
│   └── shared/{Card,StatusChip,InfoTooltip}.tsx
├── pages/{DashboardPage,MissionsPage,SettingsPage}.tsx
├── lib/
│   ├── verbs.ts                       # VERBS, VERB_CLASSES, STATUS_CLASSES, params skeletons
│   ├── linkStatus.ts                  # (lastSeenIso, now) -> 'green' | 'yellow' | 'red'
│   ├── formatTime.ts                  # timeAgo(iso)
│   └── missionState.ts                # deriveCurrentMission(commands) -> latest non-rejected ASSIGN_MISSION
└── assets/VICTUS_logo_white.png
```

## Design conventions

- **Dark theme only**: `bg-gray-950` body, `bg-gray-900 border border-gray-800` cards, `blue-600` accent.
- **No state library**. Plain `useState` + `useEffect`. Data flows top-down via props.
- **No HTTP library**. Plain `fetch` wrapped in `api.ts`. `AbortController` on every poll.
- **No icon library**. Inline SVG / emoji where needed.
- **Polling, not websockets**. 5s for slow-moving things (drones, missions), 3s for the per-drone command stream. Initial fetch staggered up to one interval to avoid thundering herd across cards.

## Mission state, briefly

The `mission` ontology object only carries an `assigned_device_ids` hint set at creation time — it is **not** the source of truth for "which mission is this drone running right now". The truth is the per-drone command stream: the latest non-rejected `ASSIGN_MISSION` command. `lib/missionState.ts:deriveCurrentMission` does that scan; `CurrentMissionPanel` renders the result. This way a drone reflects its current mission within one command-poll cycle of any reassignment, with no extra Foundry write needed.

## What's not yet wired

- **`LLMTracePanel`**, **`VideoPanel`** — placeholders. Waiting on Phase 4 streaming transforms (`last_reasoning`, `last_frame` ontology objects).
- **Real `last_seen_at`** — link dots are red because the seed is hours stale. Phase 4's `drone_state_live` transform will project the edge's live `Position` events into `drone_state_v3`.
- **Command status flips** — UI shows `PENDING` forever because the `commands_status` transform isn't built. Edge already emits `CommandAck`; the projection from telemetry → `command.status` lands in Phase 4.

## Hooking it back to design

If you're picking this up cold, start with [`pages/DashboardPage.tsx`](src/pages/DashboardPage.tsx) and [`pages/MissionsPage.tsx`](src/pages/MissionsPage.tsx) — they show the polling pattern, error-banner pattern, and how state flows down. Everything else is leaf components.
