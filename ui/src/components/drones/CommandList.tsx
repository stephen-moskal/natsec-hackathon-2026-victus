import type { Command } from "../../api/types";
import { STATUS_CLASSES } from "../../lib/verbs";
import { timeAgo } from "../../lib/formatTime";

export default function CommandList({
  commands,
  error,
  limit = 3,
}: {
  commands: Command[];
  error?: string | null;
  limit?: number;
}) {
  if (error) {
    return <div className="text-[10px] text-red-400">commands: {error}</div>;
  }
  if (commands.length === 0) {
    return <div className="text-[10px] text-gray-600 italic">no commands</div>;
  }

  return (
    <div className="space-y-1">
      {commands.slice(0, limit).map((c) => {
        const cls = STATUS_CLASSES[c.status] ?? STATUS_CLASSES.PENDING;
        return (
          <div
            key={c.message_id}
            className="flex items-center justify-between gap-2 text-[11px] py-0.5"
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${cls.bg} ${cls.text}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${cls.dot}`} />
                {c.status}
              </span>
              <span className="text-gray-200 font-mono truncate">{c.verb}</span>
            </div>
            <span className="text-[10px] text-gray-500 whitespace-nowrap">{timeAgo(c.issued_at)}</span>
          </div>
        );
      })}
    </div>
  );
}
