import type {
  Drone,
  Command,
  Mission,
  LLMReasoning,
  FoundryHealth,
  IssueCommandRequest,
  IssueCommandResult,
  CreateMissionRequest,
  AssignMissionRequest,
  AssignMissionResult,
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
  createMission: (req: CreateMissionRequest) => jpost<Mission>("/api/missions", req),
  assignMission: (req: AssignMissionRequest) =>
    jpost<AssignMissionResult[]>("/api/assign-mission", req),
  issueCommand: (req: IssueCommandRequest) =>
    jpost<IssueCommandResult[]>("/api/issue-command", req),

  /** Returns null when no LLM is configured for the device (404 from BFF). */
  reasoning: async (
    deviceId: string,
    signal?: AbortSignal,
  ): Promise<{ reasoning: LLMReasoning | null; source: "live" | "cached" | null }> => {
    const res = await fetch(
      `${BFF}/api/reasoning/${encodeURIComponent(deviceId)}`,
      { signal },
    );
    if (res.status === 404) return { reasoning: null, source: null };
    if (!res.ok) throw new Error(`GET /api/reasoning -> ${res.status}`);
    const reasoning = (await res.json()) as LLMReasoning;
    const src = res.headers.get("X-Source");
    const source = src === "live" || src === "cached" ? src : null;
    return { reasoning, source };
  },
};
