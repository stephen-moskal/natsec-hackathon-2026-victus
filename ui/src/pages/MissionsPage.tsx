import { useEffect, useState } from "react";
import PageHeader from "../components/layout/PageHeader";
import MissionEditor from "../components/missions/MissionEditor";
import MissionList from "../components/missions/MissionList";
import MissionAssignForm from "../components/missions/MissionAssignForm";
import Card from "../components/shared/Card";
import { api } from "../api/client";
import type { Drone, Mission } from "../api/types";

const MISSIONS_POLL_MS = 5000;
const DRONES_POLL_MS = 5000;

export default function MissionsPage() {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [drones, setDrones] = useState<Drone[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [missionsError, setMissionsError] = useState<string | null>(null);
  const [dronesError, setDronesError] = useState<string | null>(null);
  const [loadingMissions, setLoadingMissions] = useState(true);

  // Poll missions.
  useEffect(() => {
    const ac = new AbortController();
    let alive = true;
    async function tick() {
      try {
        const ms = await api.missions(ac.signal);
        if (!alive) return;
        setMissions(ms);
        setMissionsError(null);
      } catch (e) {
        if (!alive || ac.signal.aborted) return;
        setMissionsError(e instanceof Error ? e.message : String(e));
      } finally {
        if (alive) setLoadingMissions(false);
      }
    }
    tick();
    const id = window.setInterval(tick, MISSIONS_POLL_MS);
    return () => {
      alive = false;
      ac.abort();
      window.clearInterval(id);
    };
  }, []);

  // Poll drones (separate hook; we don't need to share with the dashboard yet).
  useEffect(() => {
    const ac = new AbortController();
    let alive = true;
    async function tick() {
      try {
        const ds = await api.drones(ac.signal);
        if (!alive) return;
        setDrones(ds);
        setDronesError(null);
      } catch (e) {
        if (!alive || ac.signal.aborted) return;
        setDronesError(e instanceof Error ? e.message : String(e));
      }
    }
    tick();
    const id = window.setInterval(tick, DRONES_POLL_MS);
    return () => {
      alive = false;
      ac.abort();
      window.clearInterval(id);
    };
  }, []);

  function handleCreated(m: Mission) {
    // Optimistic prepend; the next poll will reconcile.
    setMissions((prev) => [m, ...prev.filter((x) => x.mission_id !== m.mission_id)]);
    setSelectedId(m.mission_id);
  }

  const selectedMission = missions.find((m) => m.mission_id === selectedId) ?? null;

  return (
    <div>
      <PageHeader
        title="Missions"
        description={`${missions.length} mission${missions.length === 1 ? "" : "s"} · author the system prompt the on-board LLM will see`}
      />

      {(missionsError || dronesError) && (
        <div className="mb-4 px-3 py-2 rounded bg-red-900/30 border border-red-800/50 text-red-300 text-xs space-y-0.5">
          {missionsError && <div>missions: {missionsError}</div>}
          {dronesError && <div>drones: {dronesError}</div>}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr_320px] gap-6 items-start">
        <MissionEditor onCreated={handleCreated} />

        <Card className="space-y-3">
          <h3 className="text-sm font-semibold text-gray-100">Mission Library</h3>
          {loadingMissions && missions.length === 0 ? (
            <div className="text-xs text-gray-500 italic">Loading missions…</div>
          ) : (
            <MissionList
              missions={missions}
              selectedId={selectedId}
              onSelect={(m) => setSelectedId(m.mission_id)}
            />
          )}
        </Card>

        <MissionAssignForm drones={drones} selectedMission={selectedMission} />
      </div>
    </div>
  );
}
