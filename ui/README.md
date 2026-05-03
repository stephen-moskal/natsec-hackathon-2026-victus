# VICTUS UI — Operator Dashboard

React + Vite + TypeScript + Tailwind v4. Talks to the BFF in [`../bff/`](../bff/), never to Foundry directly. Visual conventions match the [phantomsight-annotator](/Users/smoskal/Documents/Foundry/phantomSIGHT-training/phantomsight-annotator) project.

## Quick start

```bash
# In one terminal
cd bff
cp .env.example .env       # leave MOCK_MODE=true for now
npm install
npm run dev                # starts on http://localhost:8787

# In another terminal
cd ui
cp .env.example .env       # VITE_BFF_URL=http://localhost:8787
npm install
npm run dev                # opens http://localhost:5173
```

Visit `http://localhost:5173` — should show the VICTUS logo, sidebar nav (Dashboard / Missions / Settings), and 3 mock drone cards (ALPHA / BRAVO / CHARLIE) with green link status.

## Routes

- `/` — Dashboard: drone fleet grid + (Phase 2) command palette
- `/missions` — Mission editor (Phase 3)
- `/settings` — Foundry connection health

## Layout overview

```
ui/src/
├── App.tsx                       # router
├── components/
│   ├── layout/{Sidebar,PageHeader}.tsx
│   ├── drones/{DroneGrid,DroneCard,LinkStatusDot,TelemetryPanel}.tsx
│   ├── commands/                 # Phase 2
│   ├── missions/                 # Phase 3
│   └── shared/{Card,StatusChip,InfoTooltip}.tsx
├── pages/{DashboardPage,MissionsPage,SettingsPage}.tsx
├── api/{client.ts,types.ts}      # fetch wrapper hitting /api/*
├── lib/{linkStatus.ts,formatTime.ts}
└── assets/VICTUS_logo_white.png
```

## Design conventions (matches phantomsight)

- Dark theme only: `bg-gray-950` body, `bg-gray-900 border border-gray-800` cards, `blue-600` active accent.
- Plain React state — no Redux / zustand.
- `fetch` for all HTTP — no axios / react-query.
- Logo in sidebar header at `h-6` with subtitle `text-xs text-gray-500`.

## Phase plan

See [/Users/smoskal/.claude/plans/we-have-just-created-iterative-rabin.md](../../../../../.claude/plans/we-have-just-created-iterative-rabin.md) for the full phasing. Current state: **Phase 0** (skeleton + mock BFF). Phase 1 wires real Foundry on the BFF side; UI doesn't change.
