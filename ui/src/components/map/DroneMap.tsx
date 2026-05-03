import { useEffect } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Drone } from "../../api/types";
import { linkStatusFrom } from "../../lib/linkStatus";
import { timeAgo } from "../../lib/formatTime";

// Leaflet's default icon loading breaks under Vite — supply paths explicitly.
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
});

function droneIcon(status: "green" | "red") {
  const color = status === "green" ? "#22c55e" : "#ef4444";
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 48" width="40" height="48">
      <circle cx="20" cy="20" r="14" fill="${color}" fill-opacity="0.25" stroke="${color}" stroke-width="2"/>
      <circle cx="20" cy="20" r="7" fill="${color}"/>
    </svg>`;
  return L.divIcon({
    html: svg,
    className: "",
    iconSize: [40, 40],
    iconAnchor: [20, 20],
    popupAnchor: [0, -22],
  });
}

function labelIcon(callsign: string, status: "green" | "red") {
  const color = status === "green" ? "#22c55e" : "#ef4444";
  return L.divIcon({
    html: `<div style="
      background: #111827;
      border: 1.5px solid ${color};
      color: ${color};
      font-size: 10px;
      font-weight: 700;
      font-family: ui-monospace, monospace;
      padding: 2px 6px;
      border-radius: 4px;
      white-space: nowrap;
      letter-spacing: 0.05em;
      box-shadow: 0 1px 4px rgba(0,0,0,0.5);
    ">${callsign}</div>`,
    className: "",
    iconSize: undefined,
    iconAnchor: [-12, 8],
  });
}

// Fly map to fit all drone positions whenever the drone list updates.
function FitBounds({ drones }: { drones: Drone[] }) {
  const map = useMap();
  useEffect(() => {
    const valid = drones.filter((d) => d.lat && d.lon && d.lat !== 0);
    if (valid.length === 0) return;
    const bounds = L.latLngBounds(valid.map((d) => [d.lat, d.lon]));
    map.fitBounds(bounds, { padding: [60, 60], maxZoom: 14 });
  }, [drones, map]);
  return null;
}

export default function DroneMap({ drones }: { drones: Drone[] }) {
  const validDrones = drones.filter((d) => d.lat && d.lon);

  return (
    <div className="w-full h-full rounded-lg overflow-hidden border border-gray-800">
      <MapContainer
        center={[37.78, -122.42]}
        zoom={12}
        style={{ height: "100%", width: "100%", background: "#0f172a" }}
        zoomControl={true}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
          maxZoom={20}
        />
        <FitBounds drones={validDrones} />
        {validDrones.map((drone) => {
          const status = linkStatusFrom(drone.last_seen_at);
          return (
            <div key={drone.drone_id}>
              <Marker
                position={[drone.lat, drone.lon]}
                icon={droneIcon(status)}
              >
                <Popup className="drone-popup">
                  <div style={{
                    background: "#1f2937",
                    color: "#f9fafb",
                    padding: "10px 12px",
                    borderRadius: "6px",
                    fontSize: "12px",
                    minWidth: "160px",
                    fontFamily: "ui-monospace, monospace",
                  }}>
                    <div style={{ fontWeight: 700, fontSize: "14px", marginBottom: "6px", color: status === "green" ? "#22c55e" : "#ef4444" }}>
                      {drone.callsign}
                    </div>
                    <div style={{ color: "#9ca3af", lineHeight: "1.8" }}>
                      <div>{drone.drone_id}</div>
                      <div>Lat {drone.lat.toFixed(4)}</div>
                      <div>Lon {drone.lon.toFixed(4)}</div>
                      <div>Alt {drone.alt_m}m · Hdg {drone.heading_deg}°</div>
                      <div>Battery {drone.battery_pct}%</div>
                      <div>State {drone.state}</div>
                      <div style={{ color: "#6b7280", marginTop: "4px", fontSize: "10px" }}>
                        seen {timeAgo(drone.last_seen_at)}
                      </div>
                    </div>
                  </div>
                </Popup>
              </Marker>
              <Marker
                position={[drone.lat, drone.lon]}
                icon={labelIcon(drone.callsign, status)}
                interactive={false}
              />
            </div>
          );
        })}
      </MapContainer>
    </div>
  );
}
