/** Verb dictionary for the command palette. Source of truth: shared/protocol/schemas/command.schema.json */

export type Verb =
  | "SCAN"
  | "LOITER"
  | "INVESTIGATE"
  | "FOLLOW"
  | "RTB"
  | "HOLD"
  | "ABORT"
  | "ASSIGN_MISSION";

export type Priority = "ROUTINE" | "PRIORITY" | "IMMEDIATE" | "FLASH";

export const VERBS: Verb[] = [
  "HOLD",
  "ABORT",
  "RTB",
  "SCAN",
  "LOITER",
  "INVESTIGATE",
  "FOLLOW",
  "ASSIGN_MISSION",
];

export const PRIORITIES: Priority[] = ["ROUTINE", "PRIORITY", "IMMEDIATE", "FLASH"];

/** Tailwind classes per verb — used by VerbPicker chips and command list rows. */
export const VERB_CLASSES: Record<Verb, { bg: string; text: string; border: string; hint: string }> = {
  HOLD:           { bg: "bg-gray-700",        text: "text-gray-100",   border: "border-gray-600",   hint: "Hover safely (no params)" },
  ABORT:          { bg: "bg-red-700",         text: "text-red-100",    border: "border-red-600",    hint: "Cancel intent + safe fallback" },
  RTB:            { bg: "bg-amber-700",       text: "text-amber-100",  border: "border-amber-600",  hint: "Return to base" },
  SCAN:           { bg: "bg-blue-700",        text: "text-blue-100",   border: "border-blue-600",   hint: "Sweep area, report detections" },
  LOITER:         { bg: "bg-cyan-700",        text: "text-cyan-100",   border: "border-cyan-600",   hint: "Orbit a point" },
  INVESTIGATE:    { bg: "bg-indigo-700",      text: "text-indigo-100", border: "border-indigo-600", hint: "Approach target, observe, report" },
  FOLLOW:         { bg: "bg-purple-700",      text: "text-purple-100", border: "border-purple-600", hint: "Track moving contact" },
  ASSIGN_MISSION: { bg: "bg-emerald-700",     text: "text-emerald-100",border: "border-emerald-600",hint: "Use the Missions page instead" },
};

/** Default params JSON skeleton per verb — pre-fills the params editor. */
export const VERB_PARAMS_SKELETON: Record<Verb, string> = {
  HOLD:           "{}",
  ABORT:          `{"reason": ""}`,
  RTB:            "{}",
  SCAN:           `{"area": {"type": "Polygon", "coordinates": [[[-71.06,42.36],[-71.05,42.36],[-71.05,42.37],[-71.06,42.37],[-71.06,42.36]]]}, "pattern": "grid", "altitude_m": 80}`,
  LOITER:         `{"center": {"type": "Point", "coordinates": [-71.06,42.36]}, "radius_m": 50, "altitude_m": 80}`,
  INVESTIGATE:    `{"target": {"type": "Point", "coordinates": [-71.06,42.36]}, "dwell_s": 30}`,
  FOLLOW:         `{"contact_id": "", "standoff_m": 30, "altitude_m": 80}`,
  ASSIGN_MISSION: `{"mission_id": "", "name": "", "system_prompt": ""}`,
};

/** Status chip styling for command lifecycle states. */
export const STATUS_CLASSES: Record<string, { bg: string; text: string; dot: string }> = {
  PENDING:   { bg: "bg-amber-900/40",  text: "text-amber-300",  dot: "bg-amber-400" },
  ACKED:     { bg: "bg-green-900/40",  text: "text-green-300",  dot: "bg-green-500" },
  COMPLETED: { bg: "bg-blue-900/40",   text: "text-blue-300",   dot: "bg-blue-500" },
  ABORTED:   { bg: "bg-gray-800",      text: "text-gray-400",   dot: "bg-gray-500" },
  EXPIRED:   { bg: "bg-gray-800",      text: "text-gray-500",   dot: "bg-gray-600" },
  REJECTED:  { bg: "bg-red-900/40",    text: "text-red-300",    dot: "bg-red-500" },
};
