import { useEffect, useRef, useState } from "react";
import Card from "../shared/Card";
import DroneMultiSelect from "../commands/DroneMultiSelect";
import SendResultBanner from "../commands/SendResultBanner";
import { api } from "../../api/client";
import type { Drone, Mission, AssignMissionResult } from "../../api/types";

const RESULT_DISMISS_MS = 15_000;

type Props = {
  drones: Drone[];
  selectedMission: Mission | null;
};

export default function MissionAssignForm({ drones, selectedMission }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expiresInSec, setExpiresInSec] = useState<number>(3600);
  const [sending, setSending] = useState(false);
  const [results, setResults] = useState<AssignMissionResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dismissTimerRef = useRef<number | null>(null);

  // Auto-dismiss results banner.
  useEffect(() => {
    if (!results) return;
    if (dismissTimerRef.current) window.clearTimeout(dismissTimerRef.current);
    dismissTimerRef.current = window.setTimeout(() => setResults(null), RESULT_DISMISS_MS);
    return () => {
      if (dismissTimerRef.current) window.clearTimeout(dismissTimerRef.current);
    };
  }, [results]);

  const canSend = !sending && selectedMission !== null && selected.size > 0;

  async function send(deviceIds: string[]) {
    if (!selectedMission) return;
    setError(null);
    setSending(true);
    try {
      const res = await api.assignMission({
        mission_id: selectedMission.mission_id,
        device_ids: deviceIds,
        expires_in_sec: expiresInSec,
      });
      setResults(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  return (
    <Card className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-gray-100">Assign Mission</h3>
        <p className="text-[11px] text-gray-500 mt-0.5">
          Issues an <span className="font-mono">ASSIGN_MISSION</span> command to each selected drone with the
          mission's system prompt embedded in <span className="font-mono">params_json</span>.
        </p>
      </div>

      <div className="border border-gray-800 rounded p-2 bg-gray-950/40">
        {selectedMission ? (
          <div>
            <div className="text-[10px] text-gray-500 uppercase tracking-wide">Selected Mission</div>
            <div className="text-xs font-semibold text-gray-100">{selectedMission.name}</div>
            <div className="text-[10px] text-gray-600 font-mono truncate mt-0.5">
              {selectedMission.mission_id}
            </div>
          </div>
        ) : (
          <div className="text-[11px] text-gray-500 italic">Pick a mission from the list →</div>
        )}
      </div>

      <DroneMultiSelect drones={drones} selected={selected} onChange={setSelected} />

      <div>
        <label className="block text-[10px] text-gray-500 uppercase tracking-wide mb-1">Expires in</label>
        <select
          value={expiresInSec}
          onChange={(e) => setExpiresInSec(Number(e.target.value))}
          className="w-full bg-gray-950 border border-gray-700 focus:border-blue-600 rounded px-2 py-1 text-xs text-gray-100 outline-none"
        >
          <option value={1800}>30 min</option>
          <option value={3600}>1 hour</option>
          <option value={14400}>4 hours</option>
          <option value={86400}>24 hours</option>
        </select>
      </div>

      <button
        type="button"
        disabled={!canSend}
        onClick={() => send(Array.from(selected))}
        className={`w-full text-xs font-medium px-3 py-2 rounded transition-colors ${
          canSend
            ? "bg-blue-600 text-white hover:bg-blue-500"
            : "bg-gray-800 text-gray-500 cursor-not-allowed"
        }`}
      >
        {sending
          ? "Assigning…"
          : !selectedMission
            ? "Select a mission first"
            : selected.size === 0
              ? "Select at least one drone"
              : `Assign to ${selected.size} drone${selected.size === 1 ? "" : "s"}`}
      </button>

      {error && (
        <div className="px-2 py-1.5 rounded bg-red-900/30 border border-red-800/50 text-red-300 text-[11px]">
          {error}
        </div>
      )}

      {results && (
        <SendResultBanner
          results={results}
          onRetryFailed={(ids) => send(ids)}
          onDismiss={() => setResults(null)}
        />
      )}
    </Card>
  );
}
