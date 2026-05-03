import { useState } from "react";
import type { Mission } from "../../api/types";
import { timeAgo } from "../../lib/formatTime";

type Props = {
  missions: Mission[];
  selectedId: string | null;
  onSelect: (m: Mission) => void;
};

export default function MissionList({ missions, selectedId, onSelect }: Props) {
  if (missions.length === 0) {
    return <div className="text-xs text-gray-600 italic px-1">No missions yet — create one on the left.</div>;
  }
  return (
    <div className="space-y-1.5 max-h-[60vh] overflow-auto pr-1">
      {missions.map((m) => (
        <MissionRow
          key={m.mission_id}
          mission={m}
          selected={m.mission_id === selectedId}
          onSelect={() => onSelect(m)}
        />
      ))}
    </div>
  );
}

function MissionRow({
  mission,
  selected,
  onSelect,
}: {
  mission: Mission;
  selected: boolean;
  onSelect: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const promptPreview = mission.system_prompt.length > 140
    ? `${mission.system_prompt.slice(0, 140)}…`
    : mission.system_prompt;
  return (
    <div
      className={`rounded border transition-colors cursor-pointer ${
        selected
          ? "bg-blue-900/30 border-blue-700"
          : "bg-gray-950/40 border-gray-800 hover:border-gray-700"
      }`}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between gap-2 px-3 py-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <input
              type="radio"
              checked={selected}
              onChange={onSelect}
              className="accent-blue-500"
              onClick={(e) => e.stopPropagation()}
            />
            <span className="text-xs font-semibold text-gray-100 truncate">{mission.name}</span>
            <span className="text-[10px] text-gray-500 font-mono">{mission.priority}</span>
          </div>
          {mission.description && mission.description !== "none" && (
            <div className="text-[11px] text-gray-400 mt-0.5 truncate">{mission.description}</div>
          )}
          <div className="text-[11px] text-gray-500 mt-1 leading-snug">
            {expanded ? mission.system_prompt : promptPreview}
          </div>
          {mission.system_prompt.length > 140 && (
            <button
              type="button"
              className="text-[10px] text-blue-400 hover:text-blue-300 mt-1"
              onClick={(e) => {
                e.stopPropagation();
                setExpanded((v) => !v);
              }}
            >
              {expanded ? "show less" : "show full prompt"}
            </button>
          )}
        </div>
        <div className="text-right flex flex-col items-end gap-0.5 shrink-0">
          <span className="text-[10px] text-gray-500 font-mono whitespace-nowrap">
            {timeAgo(mission.created_at)}
          </span>
          <span className="text-[10px] text-gray-600 font-mono truncate max-w-[8rem]">
            {mission.mission_id.slice(0, 8)}
          </span>
        </div>
      </div>
    </div>
  );
}
