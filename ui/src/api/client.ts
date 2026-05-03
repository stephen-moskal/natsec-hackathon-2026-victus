import type {
  Drone,
  Command,
  Mission,
  FoundryHealth,
  IssueCommandRequest,
  IssueCommandResult,
} from "./types";

const BFF = (import.meta.env.VITE_BFF_URL ?? "").replace(/\/$/, "") || "";

async function jget<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BFF}${path}`, { signal });
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

async function jpost<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BFF}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) throw new Error(`POST ${path} -> ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  health: (signal?: AbortSignal) => jget<FoundryHealth>("/api/health", signal),
  drones: (signal?: AbortSignal) => jget<Drone[]>("/api/drones", signal),
  commands: (deviceId: string, limit = 10, signal?: AbortSignal) =>
    jget<Command[]>(`/api/commands?deviceId=${encodeURIComponent(deviceId)}&limit=${limit}`, signal),
  missions: (signal?: AbortSignal) => jget<Mission[]>("/api/missions", signal),
  issueCommand: (req: IssueCommandRequest) =>
    jpost<IssueCommandResult[]>("/api/issue-command", req),
};
