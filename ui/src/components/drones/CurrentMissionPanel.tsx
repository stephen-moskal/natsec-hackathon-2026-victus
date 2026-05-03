import { useState } from "react";
import type { Command } from "../../api/types";
import { deriveCurrentMission } from "../../lib/missionState";
import { STATUS_CLASSES } from "../../lib/verbs";
import { timeAgo } from "../../lib/formatTime";

const PROMPT_PREVIEW_CHARS = 120;

export default function CurrentMissionPanel({ commands }: { commands: Command[] }) {
  const [expanded, setExpanded] = useState(false);
  const mission = deriveCurrentMission(commands);

  if (!mission) {
    return <div className="text-[11px] text-gray-600 italic">no mission assigned</div>;
  }

  const cls = STATUS_CLASSES[mission.status] ?? STATUS_CLASSES.PENDING;
  const promptPreview =
    mission.system_prompt.length > PROMPT_PREVIEW_CHARS
      ? `${mission.system_prompt.slice(0, PROMPT_PREVIEW_CHARS)}…`
      : mission.system_prompt;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-gray-100 truncate" title={mission.name}>
          {mission.name}
        </span>
        <span
          className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${cls.bg} ${cls.text}`}
          title={`assigned ${timeAgo(mission.issued_at)}`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${cls.dot}`} />
          {mission.status}
        </span>
      </div>
      {mission.system_prompt && (
        <>
          <div className="text-[11px] text-gray-400 leading-snug whitespace-pre-wrap">
            {expanded ? mission.system_prompt : promptPreview}
          </div>
          {mission.system_prompt.length > PROMPT_PREVIEW_CHARS && (
            <button
              type="button"
              className="text-[10px] text-blue-400 hover:text-blue-300"
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? "show less" : "show full prompt"}
            </button>
          )}
        </>
      )}
      <div className="text-[10px] text-gray-600 font-mono truncate" title={mission.mission_id}>
        {mission.mission_id.slice(0, 8)} · {timeAgo(mission.issued_at)}
      </div>
    </div>
  );
}
