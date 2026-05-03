import { useEffect, useState } from "react";
import PageHeader from "../components/layout/PageHeader";
import Card from "../components/shared/Card";
import { api } from "../api/client";
import type { FoundryHealth } from "../api/types";

export default function SettingsPage() {
  const [health, setHealth] = useState<FoundryHealth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    let alive = true;

    async function tick() {
      try {
        const h = await api.health(ac.signal);
        if (!alive) return;
        setHealth(h);
        setError(null);
      } catch (e) {
        if (!alive || ac.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    }
    tick();
    const id = setInterval(tick, 30_000);
    return () => {
      alive = false;
      ac.abort();
      clearInterval(id);
    };
  }, []);

  return (
    <div>
      <PageHeader title="Settings" description="BFF + Foundry connection status." />
      <Card>
        <div className="text-xs text-gray-400 uppercase tracking-wide mb-2">Foundry health</div>
        {error ? (
          <div className="text-sm text-red-400">BFF unreachable: {error}</div>
        ) : !health ? (
          <div className="text-sm text-gray-500">checking…</div>
        ) : (
          <div className="space-y-1 text-sm font-mono">
            <div>
              reachable: <span className={health.reachable ? "text-green-400" : "text-red-400"}>{String(health.reachable)}</span>
            </div>
            <div>
              token valid until: <span className="text-gray-200">{health.token_valid_until_iso ?? "—"}</span>
            </div>
            <div>
              seconds remaining: <span className="text-gray-200">{health.seconds_remaining ?? "—"}</span>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
