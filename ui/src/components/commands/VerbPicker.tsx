import { VERBS, VERB_CLASSES, VERB_PRIORITY, type Verb } from "../../lib/verbs";

export default function VerbPicker({
  value,
  onChange,
}: {
  value: Verb;
  onChange: (v: Verb) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {VERBS.map((v) => {
        const c = VERB_CLASSES[v];
        const active = v === value;
        return (
          <button
            key={v}
            type="button"
            onClick={() => onChange(v)}
            title={c.hint}
            className={`relative text-[11px] font-medium px-2 py-1.5 rounded border transition-colors text-left ${
              active
                ? `${c.bg} ${c.text} ${c.border}`
                : "bg-gray-800/40 text-gray-400 border-gray-700 hover:border-gray-600 hover:text-gray-200"
            }`}
          >
            <span
              className={`absolute top-0.5 right-1 text-[8px] font-mono ${
                active ? "opacity-70" : "text-gray-600"
              }`}
              title={`policy priority ${VERB_PRIORITY[v]}`}
            >
              P{VERB_PRIORITY[v]}
            </span>
            {v}
          </button>
        );
      })}
    </div>
  );
}
