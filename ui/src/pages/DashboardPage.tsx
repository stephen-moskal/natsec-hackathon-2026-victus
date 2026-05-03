import { useEffect, useState } from "react";
import PageHeader from "../components/layout/PageHeader";
import DroneGrid from "../components/drones/DroneGrid";
import { api } from "../api/client";
import type { Drone } from "../api/types";

const POLL_MS = 5000;

export default function DashboardPage() {
  const [drones, setDrones] = useState<Drone[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const ac = new AbortController();
    let alive = true;

    async function tick() {
      try {
        const d = await api.drones(ac.signal);
        if (!alive) return;
        setDrones(d);
        setError(null);
      } catch (e) {
        if (!alive || ac.signal.aborted) return;
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) setLoading(false);
      }
    }

    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      ac.abort();
      clearInterval(id);
    };
  }, []);

  return (
    <div>
      <PageHeader
        title="Fleet"
        description={`${drones.length} drone${drones.length === 1 ? "" : "s"} · polling every ${POLL_MS / 1000}s`}
      />
      {error && (
        <div className="mb-4 px-3 py-2 rounded bg-red-900/30 border border-red-800/50 text-red-300 text-xs">
          BFF error: {error}
        </div>
      )}
      {loading && drones.length === 0 ? (
        <div className="text-sm text-gray-500 italic">Loading fleet…</div>
      ) : (
        <DroneGrid drones={drones} />
      )}
    </div>
  );
}
