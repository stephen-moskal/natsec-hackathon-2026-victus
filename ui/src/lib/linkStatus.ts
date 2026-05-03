import type { LinkStatus } from "../api/types";

// Green if last_seen_at is within 30 minutes — covers the full pipeline latency:
// streaming dataset hot→cold flush (~5-15 min) + drone_state_live Spark build (~2 min).
// Anything beyond 30 min is genuinely LOST.
const GREEN_MS = 30 * 60_000;

export function linkStatusFrom(lastSeenIso: string, now: number = Date.now()): LinkStatus {
  if (!lastSeenIso) return "red";
  const t = Date.parse(lastSeenIso);
  if (Number.isNaN(t) || t === 0) return "red";
  return now - t < GREEN_MS ? "green" : "red";
}

export const LINK_STATUS_CLASSES: Record<LinkStatus, { dot: string; text: string; label: string }> = {
  green: { dot: "bg-green-500", text: "text-green-400", label: "ACTIVE" },
  red:   { dot: "bg-red-500",   text: "text-red-400",   label: "LOST"   },
};
