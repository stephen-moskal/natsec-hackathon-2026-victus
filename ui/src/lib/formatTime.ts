export function timeAgo(iso: string, now: number = Date.now()): string {
  if (!iso || iso === "none") return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "—";
  const dt = Math.max(0, now - t) / 1000;
  if (dt < 5) return "just now";
  if (dt < 60) return `${Math.round(dt)}s ago`;
  if (dt < 3600) return `${Math.round(dt / 60)}m ago`;
  if (dt < 86400) return `${Math.round(dt / 3600)}h ago`;
  return `${Math.round(dt / 86400)}d ago`;
}
