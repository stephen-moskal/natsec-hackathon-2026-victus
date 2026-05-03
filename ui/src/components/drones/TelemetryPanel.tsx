import type { Drone } from "../../api/types";

function fmt(n: number, digits = 4): string {
  if (typeof n !== "number" || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

export default function TelemetryPanel({ drone }: { drone: Drone }) {
  const fields: { label: string; value: string }[] = [
    { label: "Lat", value: fmt(drone.lat, 4) },
    { label: "Lon", value: fmt(drone.lon, 4) },
    { label: "Alt", value: `${fmt(drone.alt_m, 1)} m` },
    { label: "Hdg", value: `${fmt(drone.heading_deg, 0)}°` },
    { label: "Spd", value: `${fmt(drone.speed_mps, 1)} m/s` },
    { label: "Bat", value: `${fmt(drone.battery_pct, 0)}%` },
  ];
  return (
    <div className="grid grid-cols-3 gap-x-3 gap-y-1.5 text-xs font-mono">
      {fields.map((f) => (
        <div key={f.label} className="flex flex-col">
          <span className="text-[10px] text-gray-500 uppercase tracking-wide">{f.label}</span>
          <span className="text-gray-200">{f.value}</span>
        </div>
      ))}
    </div>
  );
}
