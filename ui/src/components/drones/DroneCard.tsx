import type { Drone } from "../../api/types";
import Card from "../shared/Card";
import StatusChip from "../shared/StatusChip";
import LinkStatusDot from "./LinkStatusDot";
import TelemetryPanel from "./TelemetryPanel";
import CommandList from "./CommandList";
import { linkStatusFrom } from "../../lib/linkStatus";
import { timeAgo } from "../../lib/formatTime";

export default function DroneCard({ drone }: { drone: Drone }) {
  const status = linkStatusFrom(drone.last_seen_at);
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

      {/* video placeholder */}
      <div className="relative bg-black/60 rounded border border-gray-800 aspect-video flex items-center justify-center">
        <div className="text-[11px] text-gray-600 font-mono">
          NO VIDEO · awaiting Phase 2 vision pipeline
        </div>
      </div>

      {/* telemetry */}
      <TelemetryPanel drone={drone} />

      {/* mission + state */}
      <div className="flex items-center justify-between border-t border-gray-800 pt-2 text-xs">
        <span className="text-gray-400">
          Mission: <span className="text-gray-200">{drone.current_mission_id === "none" ? "—" : drone.current_mission_id}</span>
        </span>
        <span className="text-gray-500">
          State: <span className="text-gray-200">{drone.state}</span>
        </span>
      </div>

      {/* recent commands */}
      <div className="border-t border-gray-800 pt-2">
        <div className="text-[10px] text-gray-500 uppercase tracking-wide mb-1">Recent Commands</div>
        <CommandList deviceId={drone.drone_id} />
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
