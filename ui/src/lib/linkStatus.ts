import type { LinkStatus } from "../api/types";

const GREEN_MS = 10_000;
const YELLOW_MS = 30_000;

export function linkStatusFrom(lastSeenIso: string, now: number = Date.now()): LinkStatus {
  if (!lastSeenIso) return "red";
  const t = Date.parse(lastSeenIso);
  if (Number.isNaN(t)) return "red";
  const dt = now - t;
  if (dt < GREEN_MS) return "green";
  if (dt < YELLOW_MS) return "yellow";
  return "red";
}

export const LINK_STATUS_CLASSES: Record<LinkStatus, { dot: string; text: string; label: string }> = {
  green: { dot: "bg-green-500", text: "text-green-400", label: "ACTIVE" },
  yellow: { dot: "bg-yellow-400", text: "text-yellow-300", label: "INTERMITTENT" },
  red: { dot: "bg-red-500", text: "text-red-400", label: "LOST" },
};
