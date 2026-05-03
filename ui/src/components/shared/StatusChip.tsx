import type { LinkStatus } from "../../api/types";
import { LINK_STATUS_CLASSES } from "../../lib/linkStatus";

export default function StatusChip({ status }: { status: LinkStatus }) {
  const cls = LINK_STATUS_CLASSES[status];
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-medium tracking-wide ${cls.text} bg-gray-800/60 border border-gray-700/60`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${cls.dot}`} />
      {cls.label}
    </span>
  );
}
