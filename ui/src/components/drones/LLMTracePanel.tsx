import { useEffect, useState } from "react";
import type { LLMReasoning } from "../../api/types";
import { api } from "../../api/client";
import { timeAgo } from "../../lib/formatTime";

const POLL_MS = 5000;

type Source = "live" | "cached" | null;

export default function LLMTracePanel({ droneId }: { droneId: string }) {
  const [reasoning, setReasoning] = useState<LLMReasoning | null>(null);
  const [source, setSource] = useState<Source>(null);
  const [hasLLM, setHasLLM] = useState<boolean>(true); // assume yes; flips false on 404
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    let alive = true;
    let id: number | null = null;

    async function tick() {
      try {
        const result = await api.reasoning(droneId, ac.signal);
        if (!alive) return;
        if (result.reasoning === null && result.source === null) {
          setHasLLM(false);
        } else {
          setHasLLM(true);
          setReasoning(result.reasoning);
          setSource(result.source);
        }
        setError(null);
      } catch (e) {
        if (!alive || ac.signal.aborted) return;
        const msg = e instanceof Error ? e.message : String(e);
        // 503 means edge unreachable + no cache yet — not a hard error, just no data.
        if (msg.includes("503")) {
          setError(null);
        } else {
          setError(msg);
        }
      }
    }

    tick();
    id = window.setInterval(tick, POLL_MS);
    return () => {
      alive = false;
      ac.abort();
      if (id !== null) window.clearInterval(id);
    };
  }, [droneId]);

  if (!hasLLM) {
    return <div className="text-xs text-gray-600 italic">no LLM on this drone</div>;
  }
  if (error) {
    return <div className="text-[10px] text-red-400">reasoning: {error}</div>;
  }
  if (!reasoning) {
    return <div className="text-xs text-gray-600 italic">no reasoning yet</div>;
  }

  const sourceCls = source === "cached"
    ? "bg-amber-900/40 text-amber-300"
    : "bg-green-900/40 text-green-300";

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-gray-100 truncate" title={reasoning.decision}>
          {reasoning.decision}
        </span>
        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${sourceCls}`}>
          {source ?? "—"}
        </span>
      </div>
      <div className="text-[11px] text-gray-400 leading-snug whitespace-pre-wrap">
        {reasoning.rationale}
      </div>
      <div className="flex items-center justify-between text-[10px] text-gray-600 font-mono">
        <span title={reasoning.command_id}>
          {reasoning.verb} · {reasoning.command_id.slice(0, 8)}
        </span>
        <span>
          {reasoning.tokens > 0 && <span className="mr-2">{reasoning.tokens} tok</span>}
          {timeAgo(reasoning.observed_at)}
        </span>
      </div>
    </div>
  );
}
