import type { LinkStatus } from "../../api/types";
import { LINK_STATUS_CLASSES } from "../../lib/linkStatus";

export default function LinkStatusDot({ status, withLabel = false }: { status: LinkStatus; withLabel?: boolean }) {
  const cls = LINK_STATUS_CLASSES[status];
  const ringColor =
    status === "green" ? "bg-green-500" : status === "yellow" ? "bg-yellow-400" : "bg-red-500";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="relative inline-flex h-2.5 w-2.5">
        {status === "green" && (
          <span className={`animate-ping absolute inline-flex h-2.5 w-2.5 rounded-full ${ringColor} opacity-75`} />
        )}
        <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${cls.dot}`} />
      </span>
      {withLabel && (
        <span className={`text-[10px] font-medium tracking-wide ${cls.text}`}>{cls.label}</span>
      )}
    </span>
  );
}
