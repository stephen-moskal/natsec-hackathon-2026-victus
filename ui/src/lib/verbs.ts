/** Verb dictionary for the command palette.
 *
 *  Source of truth: `drone_command_policy.json` at the repo root.
 *  These are the keywords the on-board LLM is trained to respond to.
 *  Order here matches the policy's priority field (1 = highest).
 */

export type Verb =
  | "ABORT"
  | "RTB"
  | "GOTO"
  | "ALTITUDE"
  | "LOITER"
  | "SEARCH"
  | "OBSERVE"
  | "REPORT"
  | "TRACK"
  | "IDENTIFY";

export type Priority = "ROUTINE" | "PRIORITY" | "IMMEDIATE" | "FLASH";

/** Listed in policy-priority order so the UI mirrors operational urgency. */
export const VERBS: Verb[] = [
  "ABORT",
  "RTB",
  "GOTO",
  "ALTITUDE",
  "LOITER",
  "SEARCH",
  "OBSERVE",
  "REPORT",
  "TRACK",
  "IDENTIFY",
];

export const PRIORITIES: Priority[] = ["ROUTINE", "PRIORITY", "IMMEDIATE", "FLASH"];

/** Tailwind classes per verb — color encodes intent.
 *  - ABORT/RTB: safety reds + ambers (always-execute, never-blocked verbs)
 *  - GOTO/ALTITUDE/LOITER: navigation (blue/cyan)
 *  - SEARCH/OBSERVE/TRACK: tasking (indigo/purple)
 *  - REPORT/IDENTIFY: information requests (gray/emerald)
 */
export const VERB_CLASSES: Record<Verb, { bg: string; text: string; border: string; hint: string }> = {
  ABORT:    { bg: "bg-red-700",     text: "text-red-100",    border: "border-red-600",    hint: "Halt the current task immediately and return to a safe holding state. Never blocked, executes without link." },
  RTB:      { bg: "bg-amber-700",   text: "text-amber-100",  border: "border-amber-600",  hint: "Return to base or launch point; cancels any active task." },
  GOTO:     { bg: "bg-blue-700",    text: "text-blue-100",   border: "border-blue-600",   hint: "Fly to the specified location (lat/lon, MGRS, or landmark)." },
  ALTITUDE: { bg: "bg-cyan-700",    text: "text-cyan-100",   border: "border-cyan-600",   hint: "CLIMB or DESCEND to a target altitude (feet AGL)." },
  LOITER:   { bg: "bg-sky-700",     text: "text-sky-100",    border: "border-sky-600",    hint: "Hold position for the given ISO 8601 duration." },
  SEARCH:   { bg: "bg-indigo-700",  text: "text-indigo-100", border: "border-indigo-600", hint: "Sweep an area for a plain-English target." },
  OBSERVE:  { bg: "bg-purple-700",  text: "text-purple-100", border: "border-purple-600", hint: "Pattern-of-life watch on a target/area; reports movement." },
  REPORT:   { bg: "bg-gray-700",    text: "text-gray-100",   border: "border-gray-600",   hint: "Request a SITREP — one-shot or periodic." },
  TRACK:    { bg: "bg-fuchsia-700", text: "text-fuchsia-100",border: "border-fuchsia-600",hint: "Follow a moving target while maintaining visual contact." },
  IDENTIFY: { bg: "bg-emerald-700", text: "text-emerald-100",border: "border-emerald-600",hint: "Classify a specific object: type, size, count, activity." },
};

/** Default params JSON skeleton per verb — pre-fills the params editor.
 *  Required fields are present (often empty strings the operator fills in);
 *  optional fields are present when there's a sensible default.
 */
export const VERB_PARAMS_SKELETON: Record<Verb, string> = {
  ABORT:    `{}`,
  RTB:      `{}`,
  GOTO:     `{\n  "destination": ""\n}`,
  ALTITUDE: `{\n  "direction": "CLIMB",\n  "altitude": 400\n}`,
  LOITER:   `{\n  "duration": "PT10M"\n}`,
  SEARCH:   `{\n  "area": "",\n  "target": "",\n  "pattern": "parallel sweep"\n}`,
  OBSERVE:  `{\n  "target": "",\n  "duration": "PT30M",\n  "reportInterval": "PT60S"\n}`,
  REPORT:   `{\n  "subject": "current scene"\n}`,
  TRACK:    `{\n  "target": "",\n  "standOffMeters": 30\n}`,
  IDENTIFY: `{\n  "target": ""\n}`,
};

/** Natural-language examples from the policy — shown as ghost text under the params editor. */
export const VERB_EXAMPLES: Record<Verb, string[]> = {
  ABORT:    ["Abort.", "Stop, abort the mission.", "Knock it off."],
  RTB:      ["Come home.", "Return to base.", "RTB now."],
  GOTO:     ["Go to the lighthouse.", "Fly to grid 38SMB1234.", "Move to lat 33.5 lon -106.4."],
  ALTITUDE: ["Climb to 400 feet.", "Descend to 200 AGL.", "Get up to angels four."],
  LOITER:   ["Hold here for 10 minutes.", "Loiter over the bridge for half an hour."],
  SEARCH:   ["Search the harbor for small boats.", "Sweep the field for vehicles."],
  OBSERVE:  ["Watch that pier for 10 minutes.", "Observe the warehouse, tell me when something changes."],
  REPORT:   ["What do you see?", "Give me a SITREP every 5 minutes.", "Status please."],
  TRACK:    ["Track that truck.", "Follow the boat heading north."],
  IDENTIFY: ["Identify the vessel at the pier.", "What is that vehicle?"],
};

/** Numeric priority from the policy file. Lower = higher precedence on the wire. */
export const VERB_PRIORITY: Record<Verb, number> = {
  ABORT: 1, RTB: 2, GOTO: 3, ALTITUDE: 4, LOITER: 5,
  SEARCH: 6, OBSERVE: 7, REPORT: 8, TRACK: 9, IDENTIFY: 10,
};

/** Status chip styling for command lifecycle states (Foundry side).
 *  These match the protocol's 5-state machine plus drone reply keywords.
 */
export const STATUS_CLASSES: Record<string, { bg: string; text: string; dot: string }> = {
  PENDING:   { bg: "bg-amber-900/40",  text: "text-amber-300",  dot: "bg-amber-400" },
  ACKED:     { bg: "bg-green-900/40",  text: "text-green-300",  dot: "bg-green-500" },
  COMPLETED: { bg: "bg-blue-900/40",   text: "text-blue-300",   dot: "bg-blue-500" },
  ABORTED:   { bg: "bg-gray-800",      text: "text-gray-400",   dot: "bg-gray-500" },
  EXPIRED:   { bg: "bg-gray-800",      text: "text-gray-500",   dot: "bg-gray-600" },
  REJECTED:  { bg: "bg-red-900/40",    text: "text-red-300",    dot: "bg-red-500" },
  WILCO:     { bg: "bg-green-900/40",  text: "text-green-300",  dot: "bg-green-500" },
  UNABLE:    { bg: "bg-red-900/40",    text: "text-red-300",    dot: "bg-red-500" },
  ROGER:     { bg: "bg-blue-900/40",   text: "text-blue-300",   dot: "bg-blue-500" },
  STANDBY:   { bg: "bg-amber-900/40",  text: "text-amber-300",  dot: "bg-amber-400" },
};
