import { useState } from "react";

interface InfoTooltipProps {
  text: string;
}

export default function InfoTooltip({ text }: InfoTooltipProps) {
  const [show, setShow] = useState(false);

  return (
    <span
      className="relative inline-flex ml-1 align-middle"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      <span className="w-3.5 h-3.5 rounded-full bg-gray-700 text-gray-400 text-[9px] font-bold
        inline-flex items-center justify-center cursor-help select-none hover:bg-gray-600 hover:text-gray-300 transition-colors">
        ?
      </span>
      {show && (
        <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 px-2.5 py-1.5
          bg-gray-800 border border-gray-700 text-xs text-gray-200 rounded-lg shadow-lg
          whitespace-normal w-56 z-50 leading-relaxed pointer-events-none">
          {text}
        </span>
      )}
    </span>
  );
}

export function Label({ children, tip }: { children: React.ReactNode; tip?: string }) {
  return (
    <label className="block text-xs text-gray-400 mb-1">
      {children}
      {tip && <InfoTooltip text={tip} />}
    </label>
  );
}
