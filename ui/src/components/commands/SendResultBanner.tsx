import type { IssueCommandResult } from "../../api/types";

export default function SendResultBanner({
  results,
  onRetryFailed,
  onDismiss,
}: {
  results: IssueCommandResult[];
  onRetryFailed?: (deviceIds: string[]) => void;
  onDismiss: () => void;
}) {
  const failed = results.filter((r) => !r.ok).map((r) => r.device_id);
  const ok = results.filter((r) => r.ok).length;
  return (
    <div className="border border-gray-700 bg-gray-900 rounded p-2 space-y-1.5 text-xs">
      <div className="flex items-center justify-between">
        <span className="text-gray-300">
          {ok}/{results.length} sent
        </span>
        <button onClick={onDismiss} className="text-gray-500 hover:text-gray-300 text-[10px]">
          dismiss
        </button>
      </div>
      <div className="flex flex-wrap gap-1">
        {results.map((r) => (
          <span
            key={r.device_id}
            title={r.error}
            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono ${
              r.ok
                ? "bg-green-900/40 text-green-300"
                : "bg-red-900/40 text-red-300"
            }`}
          >
            <span>{r.ok ? "✓" : "✗"}</span>
            <span>{r.device_id}</span>
          </span>
        ))}
      </div>
      {failed.length > 0 && onRetryFailed && (
        <button
          type="button"
          onClick={() => onRetryFailed(failed)}
          className="w-full text-[11px] px-2 py-1 rounded bg-red-700/30 border border-red-700 text-red-200 hover:bg-red-700/50"
        >
          Retry {failed.length} failed
        </button>
      )}
    </div>
  );
}
