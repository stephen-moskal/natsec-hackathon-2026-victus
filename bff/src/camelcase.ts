/** snake_case <-> camelCase translation maps for Foundry property API names.
 *
 * Foundry's auto-converter rewrites property IDs at deploy time. Some
 * conversions are creative (lat -> latitude, battery_pct -> batteryPercentage).
 * The maps below are the canonical truth — keep them in sync with the property
 * tables in foundry/README.md.
 */

import type { Drone, Command, Mission } from "./types.js";

// ── drone ──────────────────────────────────────────────────────────────────

const DRONE_C2S: Record<string, keyof Drone> = {
  droneId: "drone_id",
  callsign: "callsign",
  protocolVersion: "protocol_version",
  lastSeenAt: "last_seen_at",
  latitude: "lat",
  longitude: "lon",
  altitudeM: "alt_m",
  headingDeg: "heading_deg",
  speedMs: "speed_mps",
  batteryPercentage: "battery_pct",
  state: "state",
  currentMissionId: "current_mission_id",
  linkStatus: "link_status",
};

export function droneFromFoundry(obj: Record<string, unknown>): Drone {
  const out: Record<string, unknown> = {};
  for (const [camel, snake] of Object.entries(DRONE_C2S)) {
    out[snake] = obj[camel] ?? "";
  }
  return out as Drone;
}

// ── command ────────────────────────────────────────────────────────────────

const COMMAND_C2S: Record<string, keyof Command> = {
  messageId: "message_id",
  deviceId: "device_id",
  missionId: "mission_id",
  verb: "verb",
  paramsJson: "params_json",
  priority: "priority",
  status: "status",
  issuedAt: "issued_at",
  expiresAt: "expires_at",
  ackedAt: "acked_at",
  completedAt: "completed_at",
  supersedes: "supersedes",
};

export function commandFromFoundry(obj: Record<string, unknown>): Command {
  const out: Record<string, unknown> = {};
  for (const [camel, snake] of Object.entries(COMMAND_C2S)) {
    out[snake] = obj[camel] ?? "";
  }
  return out as Command;
}

// ── mission (Phase 3) ──────────────────────────────────────────────────────

const MISSION_C2S: Record<string, keyof Mission> = {
  missionId: "mission_id",
  name: "name",
  description: "description",
  systemPrompt: "system_prompt",
  priority: "priority",
  roeProfile: "roe_profile",
  active: "active",
  assignedDeviceIds: "assigned_device_ids",
  createdAt: "created_at",
  updatedAt: "updated_at",
};

export function missionFromFoundry(obj: Record<string, unknown>): Mission {
  const out: Record<string, unknown> = {};
  for (const [camel, snake] of Object.entries(MISSION_C2S)) {
    out[snake] = obj[camel] ?? "";
  }
  return out as Mission;
}
