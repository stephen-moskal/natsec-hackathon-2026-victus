# Workshop dashboard — Operator Console

Single-page operator view. Built around three panes.

## Layout

```
+-------------------------------------------------------------+
|  Fleet header: per-drone chips (callsign, state, link)      |
+-----------------------------+-------------------------------+
|                             |  Selected drone:              |
|                             |   - Status / battery          |
|         Map widget          |   - Current command           |
|         (drone positions,   |   - Reasoning trace feed      |
|          last detections)   |   - Last detection thumbnail  |
|                             |                               |
|                             |  Command palette:             |
|                             |   [SCAN] [LOITER] [INVESTIGATE]|
|                             |   [FOLLOW] [RTB] [HOLD] [ABORT]|
+-----------------------------+-------------------------------+
|  Mission timeline: commands issued / acks / mission events   |
+-------------------------------------------------------------+
```

## Variables

| Variable | Type | Source |
|---|---|---|
| `selectedDroneId` | string | clicked chip / map marker |
| `fleet` | object set | `drone` ontology |
| `selectedDrone` | object | filter `fleet` by `selectedDroneId` |
| `recentCommands` | object set | `command` filtered by `drone_id` and `issued_at > now - 1h` |
| `recentTraces` | object set | `reasoning-trace` filtered same |
| `recentDetections` | object set | `detection` filtered same |

## Action wiring

Each command palette button opens an action form pre-filled with the selected drone:

| Button | Action | Form fields |
|---|---|---|
| SCAN | Issue Command (verb=SCAN) | area picker (map draw), pattern, altitude_m, priority, expires_at |
| LOITER | Issue Command (verb=LOITER) | center (map click), radius_m, altitude_m, priority, expires_at |
| INVESTIGATE | Issue Command (verb=INVESTIGATE) | target (detection picker or map click), dwell_s, priority, expires_at |
| FOLLOW | Issue Command (verb=FOLLOW) | contact_id, standoff_m, altitude_m, priority, expires_at |
| RTB | Issue Command (verb=RTB) | base (optional), priority |
| HOLD | Issue Command (verb=HOLD) | priority |
| ABORT | Issue Command (verb=ABORT) | reason, priority=IMMEDIATE |

## Notes

- Map widget needs `drone.geo_point` (GeoPoint) and `detection.geo_point`. If those are STRING in the ontology, the widget will not render — convert to GeoPoint before Phase 2.
- Reasoning trace feed should be a simple list ordered by `at desc`, capped at the most recent 50.
- Mission timeline can be a table for the demo; nice-to-have is a Gantt-style widget.
