import { useMemo } from "react";

export default function ParamsEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}) {
  const status = useMemo<{ ok: boolean; msg: string }>(() => {
    if (value.trim() === "") return { ok: false, msg: "empty" };
    try {
      JSON.parse(value);
      return { ok: true, msg: "valid JSON" };
    } catch (e) {
      return { ok: false, msg: e instanceof Error ? e.message : "invalid JSON" };
    }
  }, [value]);

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-gray-500 uppercase tracking-wide">Params (JSON)</span>
        <span className={`text-[10px] ${status.ok ? "text-green-400" : "text-red-400"}`}>
          {status.ok ? "✓" : "✗"} {status.msg}
        </span>
      </div>
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={5}
        spellCheck={false}
        className="w-full bg-gray-950 border border-gray-700 focus:border-blue-600 rounded px-2 py-1.5 text-[11px] font-mono text-gray-100 outline-none resize-y"
      />
    </div>
  );
}
