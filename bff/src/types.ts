/** Wire types between BFF and UI. Snake_case to match the protocol envelope. */

export type Drone = {
  drone_id: string;
  callsign: string;
  protocol_version: string;
  last_seen_at: string;
  lat: number;
  lon: number;
  alt_m: number;
  heading_deg: number;
  speed_mps: number;
  battery_pct: number;
  state: string;
  current_mission_id: string;
  link_status: string;
};

export type Command = {
  message_id: string;
  device_id: string;
  mission_id: string;
  verb: string;
  params_json: string;
  priority: string;
  status: string;
  issued_at: string;
  expires_at: string;
  acked_at: string;
  completed_at: string;
  supersedes: string;
};

export type Mission = {
  mission_id: string;
  name: string;
  description: string;
  system_prompt: string;
  objectives: string;
  target_specs: string;
  area_geo_json: string;
  priority: string;
  roe_profile: string;
  active: string;
  assigned_device_ids: string;
  created_at: string;
  updated_at: string;
};

export type CreateMissionRequest = {
  name: string;
  description: string;
  system_prompt: string;
  objectives?: string;
  target_specs?: string;
  area_geo_json?: string;
  priority?: string;       // default ROUTINE
  roe_profile?: string;    // default roe-default
};

export type AssignMissionRequest = {
  mission_id: string;
  device_ids: string[];
  expires_in_sec?: number; // default 3600
};

export type AssignMissionResult = {
  device_id: string;
  ok: boolean;
  message_id?: string;
  error?: string;
};

export type CommandAck = {
  command_id: string;
  device_id: string;
  result: string;   // WILCO | ROGER | STANDBY | UNABLE | EXPIRED
  reason: string;
  acked_at: string;
};

export type FoundryHealth = {
  reachable: boolean;
  token_valid_until_iso: string | null;
  seconds_remaining: number | null;
};

export type IssueCommandRequest = {
  device_ids: string[];
  verb: string;
  params_json: string;
  priority: string;
  expires_in_sec: number;
};

export type IssueCommandResult = {
  device_id: string;
  ok: boolean;
  message_id?: string;
  error?: string;
};
