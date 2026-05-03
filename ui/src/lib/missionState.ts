/** Helpers for deriving "the mission this drone is currently carrying" from
 *  the per-drone command stream. The source of truth is the most recent
 *  ASSIGN_MISSION command that did not get rejected (UNABLE / REJECTED).
 *
 *  We can't reach into the mission ontology object directly per-drone — that
 *  table only carries `assigned_device_ids` as a creation-time hint. The
 *  command stream is the live truth, so we mine it here.
 */

import type { Command } from "../api/types";

export type CurrentMission = {
  command_id: string;
  mission_id: string;
  name: string;
  system_prompt: string;
  status: string;
  issued_at: string;
};

const REJECT_STATES = new Set(["REJECTED", "UNABLE", "EXPIRED", "ABORTED"]);

export function deriveCurrentMission(commands: Command[]): CurrentMission | null {
  // Commands come back issuedAt-desc from the BFF; first non-rejected
  // ASSIGN_MISSION wins.
  for (const c of commands) {
    if (c.verb !== "ASSIGN_MISSION") continue;
    if (REJECT_STATES.has(c.status)) continue;
    let parsed: Record<string, unknown> = {};
    try {
      parsed = JSON.parse(c.params_json) as Record<string, unknown>;
    } catch {
      continue; // malformed payload — skip and look further back
    }
    return {
      command_id: c.message_id,
      mission_id: String(parsed.mission_id ?? c.mission_id ?? ""),
      name: String(parsed.name ?? "(unnamed)"),
      system_prompt: String(parsed.system_prompt ?? ""),
      status: c.status,
      issued_at: c.issued_at,
    };
  }
  return null;
}
