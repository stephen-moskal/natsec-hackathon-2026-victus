import type { Drone } from "../../api/types";
import { linkStatusFrom, LINK_STATUS_CLASSES } from "../../lib/linkStatus";

export default function DroneMultiSelect({
  drones,
  selected,
  onChange,
}: {
  drones: Drone[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
}) {
  function toggle(id: string) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onChange(next);
  }
  function selectAll() {
    onChange(new Set(drones.map((d) => d.drone_id)));
  }
  function clear() {
    onChange(new Set());
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-gray-500 uppercase tracking-wide">
          Targets ({selected.size}/{drones.length})
        </span>
        <div className="flex gap-2 text-[10px]">
          <button
            type="button"
            onClick={selectAll}
            className="text-blue-400 hover:text-blue-300"
          >
            all
          </button>
          <button
            type="button"
            onClick={clear}
            className="text-gray-500 hover:text-gray-300"
          >
            clear
          </button>
        </div>
      </div>
      <div className="space-y-0.5 max-h-48 overflow-auto">
        {drones.length === 0 && (
          <div className="text-[11px] text-gray-600 italic px-1 py-2">No drones</div>
        )}
        {drones.map((d) => {
          const status = linkStatusFrom(d.last_seen_at);
          const cls = LINK_STATUS_CLASSES[status];
          const checked = selected.has(d.drone_id);
          return (
            <label
              key={d.drone_id}
              className={`flex items-center gap-2 px-2 py-1.5 rounded text-xs cursor-pointer ${
                checked ? "bg-blue-900/30 border border-blue-800/60" : "border border-transparent hover:bg-gray-800/40"
              }`}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={() => toggle(d.drone_id)}
                className="accent-blue-500"
              />
              <span className={`w-1.5 h-1.5 rounded-full ${cls.dot}`} />
              <span className="text-gray-100 font-medium">{d.callsign}</span>
              <span className="text-[10px] text-gray-500 font-mono">{d.drone_id}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
}
