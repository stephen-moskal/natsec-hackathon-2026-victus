import { useEffect, useRef, useState } from "react";
import Card from "../shared/Card";
import VerbPicker from "./VerbPicker";
import DroneMultiSelect from "./DroneMultiSelect";
import ParamsEditor from "./ParamsEditor";
import SendResultBanner from "./SendResultBanner";
import { VERB_PARAMS_SKELETON, PRIORITIES, type Verb, type Priority } from "../../lib/verbs";
import { api } from "../../api/client";
import type { Drone, IssueCommandResult } from "../../api/types";

const RESULT_DISMISS_MS = 15_000;

export default function CommandPalette({ drones }: { drones: Drone[] }) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [verb, setVerb] = useState<Verb>("HOLD");
  const [priority, setPriority] = useState<Priority>("PRIORITY");
  const [paramsJson, setParamsJson] = useState<string>(VERB_PARAMS_SKELETON.HOLD);
  const [expiresInSec, setExpiresInSec] = useState<number>(3600);
  const [sending, setSending] = useState(false);
  const [results, setResults] = useState<IssueCommandResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const dismissTimerRef = useRef<number | null>(null);

  // Re-pre-fill params skeleton when verb changes (only if current value matches the previous skeleton).
  const prevVerbRef = useRef<Verb>(verb);
  useEffect(() => {
    if (prevVerbRef.current !== verb) {
      const prevSkeleton = VERB_PARAMS_SKELETON[prevVerbRef.current];
      if (paramsJson.trim() === prevSkeleton.trim()) {
        setParamsJson(VERB_PARAMS_SKELETON[verb]);
      }
      prevVerbRef.current = verb;
    }
  }, [verb, paramsJson]);

  // Auto-dismiss results banner.
  useEffect(() => {
    if (!results) return;
    if (dismissTimerRef.current) window.clearTimeout(dismissTimerRef.current);
    dismissTimerRef.current = window.setTimeout(() => setResults(null), RESULT_DISMISS_MS);
    return () => {
      if (dismissTimerRef.current) window.clearTimeout(dismissTimerRef.current);
    };
  }, [results]);

  // Validate JSON live.
  let paramsValid = false;
  try {
    JSON.parse(paramsJson);
    paramsValid = true;
  } catch {
    /* noop */
  }

  const canSend = !sending && selected.size > 0 && paramsValid;

  async function send(deviceIds: string[]) {
    setError(null);
    setSending(true);
    try {
      const res = await api.issueCommand({
        device_ids: deviceIds,
        verb,
        params_json: paramsJson,
        priority,
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
    <Card className="space-y-3 sticky top-0">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-100">Command Palette</h3>
        <span className="text-[10px] text-gray-500 font-mono">v{0.2}</span>
      </div>

      <DroneMultiSelect drones={drones} selected={selected} onChange={setSelected} />

      <div className="border-t border-gray-800 pt-2 space-y-1">
        <span className="text-[10px] text-gray-500 uppercase tracking-wide">Verb</span>
        <VerbPicker value={verb} onChange={setVerb} />
      </div>

      <div className="border-t border-gray-800 pt-2 grid grid-cols-2 gap-2">
        <div>
          <label className="block text-[10px] text-gray-500 uppercase tracking-wide mb-1">Priority</label>
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value as Priority)}
            className="w-full bg-gray-950 border border-gray-700 focus:border-blue-600 rounded px-2 py-1 text-xs text-gray-100 outline-none"
          >
            {PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-[10px] text-gray-500 uppercase tracking-wide mb-1">Expires in</label>
          <select
            value={expiresInSec}
            onChange={(e) => setExpiresInSec(Number(e.target.value))}
            className="w-full bg-gray-950 border border-gray-700 focus:border-blue-600 rounded px-2 py-1 text-xs text-gray-100 outline-none"
          >
            <option value={300}>5 min</option>
            <option value={1800}>30 min</option>
            <option value={3600}>1 hour</option>
            <option value={14400}>4 hours</option>
          </select>
        </div>
      </div>

      <div className="border-t border-gray-800 pt-2">
        <ParamsEditor value={paramsJson} onChange={setParamsJson} />
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
          ? "Sending…"
          : selected.size === 0
            ? "Select at least one drone"
            : !paramsValid
              ? "Invalid params JSON"
              : `Send ${verb} to ${selected.size} drone${selected.size === 1 ? "" : "s"}`}
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
