import type { Drone } from "../../api/types";
import DroneCard from "./DroneCard";

export default function DroneGrid({ drones }: { drones: Drone[] }) {
  if (drones.length === 0) {
    return (
      <div className="text-sm text-gray-500 italic p-8 text-center border border-dashed border-gray-800 rounded-lg">
        No drones in the fleet yet.
      </div>
    );
  }
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {drones.map((d) => (
        <DroneCard key={d.drone_id} drone={d} />
      ))}
    </div>
  );
}
