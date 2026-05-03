import { useEffect, useState } from "react";
import PageHeader from "../components/layout/PageHeader";
import DroneMap from "../components/map/DroneMap";
import { api } from "../api/client";
import type { Drone } from "../api/types";

const POLL_MS = 5000;

export default function MapPage() {
  const [drones, setDrones] = useState<Drone[]>([]);
  const [error, setError] = useState<string | null>(null);

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
      }
    }

    tick();
    const id = window.setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      ac.abort();
      window.clearInterval(id);
    };
  }, []);

  const online = drones.filter((d) => d.link_status === "ONLINE").length;

  return (
    <div className="flex flex-col h-full">
      <PageHeader
        title="Map"
        description={`${online} active · ${drones.length} total · polling every ${POLL_MS / 1000}s`}
      />
      {error && (
        <div className="mb-4 px-3 py-2 rounded bg-red-900/30 border border-red-800/50 text-red-300 text-xs">
          BFF error: {error}
        </div>
      )}
      <div className="flex-1 min-h-0" style={{ height: "calc(100vh - 120px)" }}>
        <DroneMap drones={drones} />
      </div>
    </div>
  );
}
