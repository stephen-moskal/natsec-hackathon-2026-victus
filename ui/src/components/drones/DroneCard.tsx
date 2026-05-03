import { useEffect, useRef, useState } from "react";
import type { Command, Drone } from "../../api/types";
import Card from "../shared/Card";
import StatusChip from "../shared/StatusChip";
import LinkStatusDot from "./LinkStatusDot";
import TelemetryPanel from "./TelemetryPanel";
import CommandList from "./CommandList";
import CurrentMissionPanel from "./CurrentMissionPanel";
import { api } from "../../api/client";
import { linkStatusFrom } from "../../lib/linkStatus";
import { timeAgo } from "../../lib/formatTime";

const COMMANDS_POLL_MS = 3000;
const VIDEO_REFRESH_MS = 1000; // 1 fps — low bandwidth, still feels live

function VideoFeed({ droneId }: { droneId: string }) {
  const [ts, setTs] = useState(() => Date.now());
  const [hasFrame, setHasFrame] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    // Tick updates the src; the img stays in the DOM so the browser handles
    // its own caching and retry — no React unmount/remount flicker.
    timerRef.current = window.setInterval(() => setTs(Date.now()), VIDEO_REFRESH_MS);
    return () => { if (timerRef.current) window.clearInterval(timerRef.current); };
  }, []);

  const src = `/api/frame/${encodeURIComponent(droneId)}?t=${ts}`;

  return (
    <div className="relative bg-black rounded border border-gray-800 aspect-video overflow-hidden">
      {/* Always in DOM — browser handles retry silently on each tick */}
      <img
        src={src}
        alt={`${droneId} camera`}
        className={`w-full h-full object-cover transition-opacity duration-300 ${hasFrame ? "opacity-100" : "opacity-0"}`}
        onLoad={() => setHasFrame(true)}
        onError={() => setHasFrame(false)}
      />
      {/* Overlay shown only when no frame is available */}
      {!hasFrame && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-[11px] text-gray-600 font-mono">NO VIDEO</span>
        </div>
      )}
    </div>
  );
}
const COMMANDS_LIMIT = 10; // need a few extra so CurrentMissionPanel can scan back past stale ASSIGN_MISSIONs

export default function DroneCard({ drone }: { drone: Drone }) {
  const status = linkStatusFrom(drone.last_seen_at);
  const [commands, setCommands] = useState<Command[]>([]);
  const [commandsError, setCommandsError] = useState<string | null>(null);

  // Single command poll per card, shared by CommandList + CurrentMissionPanel.
  useEffect(() => {
    const ac = new AbortController();
    let alive = true;
    let id: number | null = null;

    async function tick() {
      try {
        const cs = await api.commands(drone.drone_id, COMMANDS_LIMIT, ac.signal);
        if (!alive) return;
        setCommands(cs);
        setCommandsError(null);
      } catch (e) {
        if (!alive || ac.signal.aborted) return;
        setCommandsError(e instanceof Error ? e.message : String(e));
      }
    }

    // Stagger initial fetch by up to one poll interval to avoid thundering herd.
    const startDelay = Math.random() * COMMANDS_POLL_MS;
    const startTimer = window.setTimeout(() => {
      tick();
      id = window.setInterval(tick, COMMANDS_POLL_MS);
    }, startDelay);

    return () => {
      alive = false;
      ac.abort();
      window.clearTimeout(startTimer);
      if (id !== null) window.clearInterval(id);
    };
  }, [drone.drone_id]);

  return (
    <Card className="flex flex-col gap-3">
      {/* header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <LinkStatusDot status={status} />
          <h3 className="text-sm font-semibold text-gray-100">{drone.callsign}</h3>
          <span className="text-[10px] text-gray-500 font-mono">{drone.drone_id}</span>
        </div>
        <StatusChip status={status} />
      </div>

      {/* live video feed */}
      <VideoFeed droneId={drone.drone_id} />

      {/* telemetry */}
      <TelemetryPanel drone={drone} />

      {/* state line */}
      <div className="flex items-center justify-between border-t border-gray-800 pt-2 text-xs">
        <span className="text-gray-500">
          State: <span className="text-gray-200">{drone.state}</span>
        </span>
      </div>

      {/* current mission (derived from latest accepted ASSIGN_MISSION) */}
      <div className="border-t border-gray-800 pt-2">
        <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1">Current Mission</div>
        <CurrentMissionPanel commands={commands} />
      </div>

      {/* recent commands */}
      <div className="border-t border-gray-800 pt-2">
        <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1">Recent Commands</div>
        <CommandList commands={commands} error={commandsError} />
      </div>

      {/* LLM trace placeholder */}
      <div className="border-t border-gray-800 pt-2">
        <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1">LLM Reasoning</div>
        <div className="text-xs text-gray-600 italic">awaiting Phase 4 transform · last_reasoning</div>
      </div>

      {/* footer */}
      <div className="flex items-center justify-between text-[10px] text-gray-500 font-mono pt-1">
        <span>seen {timeAgo(drone.last_seen_at)}</span>
        <span>proto {drone.protocol_version}</span>
      </div>
    </Card>
  );
}
