import express, { type Request, type Response } from "express";
import cors from "cors";
import dotenv from "dotenv";
import type {
  Drone,
  Command,
  FoundryHealth,
  IssueCommandRequest,
  IssueCommandResult,
} from "./types.js";
import {
  type FoundryConfig,
  searchObjects,
  applyAction,
  pingFoundry,
  decodeTokenExpiry,
} from "./foundry.js";
import { droneFromFoundry, commandFromFoundry } from "./camelcase.js";

dotenv.config();

const PORT = Number(process.env.BFF_PORT ?? 8787);
const ORIGIN = process.env.ALLOWED_ORIGIN ?? "http://localhost:5173";
const MOCK_MODE = (process.env.MOCK_MODE ?? "true").toLowerCase() === "true";

const FOUNDRY: FoundryConfig = {
  stackUrl: (process.env.FOUNDRY_STACK_URL ?? "").replace(/\/$/, ""),
  ontology: process.env.FOUNDRY_ONTOLOGY ?? "",
  token: process.env.FOUNDRY_TOKEN ?? "",
};

if (!MOCK_MODE) {
  if (!FOUNDRY.stackUrl || !FOUNDRY.ontology || !FOUNDRY.token) {
    console.error("[bff] MOCK_MODE=false but FOUNDRY_STACK_URL / FOUNDRY_ONTOLOGY / FOUNDRY_TOKEN missing");
    process.exit(1);
  }
}

const app = express();
app.use(cors({ origin: ORIGIN }));
app.use(express.json({ limit: "1mb" }));

// ───────────────────────────────────────────────────────────────────────────
// Mock data (used when MOCK_MODE=true)
// ───────────────────────────────────────────────────────────────────────────

function mockDrones(): Drone[] {
  const nowIso = new Date().toISOString();
  return [
    { drone_id: "uav-01", callsign: "ALPHA", protocol_version: "0.2.0", last_seen_at: nowIso, lat: 42.3601, lon: -71.0589, alt_m: 100, heading_deg: 90, speed_mps: 0, battery_pct: 95, state: "NOMINAL", current_mission_id: "none", link_status: "ONLINE" },
    { drone_id: "uav-02", callsign: "BRAVO", protocol_version: "0.2.0", last_seen_at: nowIso, lat: 42.3651, lon: -71.0552, alt_m: 120, heading_deg: 180, speed_mps: 0, battery_pct: 88, state: "NOMINAL", current_mission_id: "none", link_status: "ONLINE" },
    { drone_id: "uav-03", callsign: "CHARLIE", protocol_version: "0.2.0", last_seen_at: nowIso, lat: 42.3550, lon: -71.0633, alt_m: 110, heading_deg: 270, speed_mps: 0, battery_pct: 72, state: "NOMINAL", current_mission_id: "none", link_status: "ONLINE" },
  ];
}

// ───────────────────────────────────────────────────────────────────────────
// Routes
// ───────────────────────────────────────────────────────────────────────────

app.get("/api/health", async (_req: Request, res: Response<FoundryHealth>) => {
  if (MOCK_MODE) {
    res.json({ reachable: false, token_valid_until_iso: null, seconds_remaining: null });
    return;
  }
  const reachable = await pingFoundry(FOUNDRY);
  const { exp, iso } = decodeTokenExpiry(FOUNDRY.token);
  const secondsRemaining = exp ? Math.max(0, exp - Math.floor(Date.now() / 1000)) : null;
  res.json({
    reachable,
    token_valid_until_iso: iso,
    seconds_remaining: secondsRemaining,
  });
});

app.get("/api/drones", async (_req: Request, res: Response) => {
  if (MOCK_MODE) {
    res.json(mockDrones());
    return;
  }
  try {
    const objs = await searchObjects(FOUNDRY, "drone", { pageSize: 100 });
    const drones: Drone[] = objs.map(droneFromFoundry);
    res.json(drones);
  } catch (e) {
    console.error("[bff] /api/drones error:", e);
    res.status(502).json({ error: e instanceof Error ? e.message : String(e) });
  }
});

app.get("/api/commands", async (req: Request, res: Response) => {
  if (MOCK_MODE) {
    res.json([]);
    return;
  }
  const deviceId = String(req.query.deviceId ?? "");
  const limit = Math.min(Number(req.query.limit ?? 10), 100);
  if (!deviceId) {
    res.status(400).json({ error: "deviceId query param required" });
    return;
  }
  try {
    const objs = await searchObjects(FOUNDRY, "command", {
      where: { type: "eq", field: "deviceId", value: deviceId },
      orderBy: { fields: [{ field: "issuedAt", direction: "desc" }] },
      pageSize: limit,
    });
    const commands: Command[] = objs.map(commandFromFoundry);
    res.json(commands);
  } catch (e) {
    console.error("[bff] /api/commands error:", e);
    res.status(502).json({ error: e instanceof Error ? e.message : String(e) });
  }
});

app.get("/api/missions", (_req: Request, res: Response) => {
  res.json([]); // Phase 3
});

app.post("/api/issue-command", async (req: Request, res: Response<IssueCommandResult[]>) => {
  const body = req.body as IssueCommandRequest;
  if (!body || !Array.isArray(body.device_ids) || body.device_ids.length === 0) {
    res.status(400).json([]);
    return;
  }

  if (MOCK_MODE) {
    const results: IssueCommandResult[] = body.device_ids.map((id) => ({
      device_id: id,
      ok: true,
      message_id: crypto.randomUUID(),
    }));
    res.json(results);
    return;
  }

  // Validate params_json before fan-out (BFF re-checks even though UI does too).
  try {
    JSON.parse(body.params_json);
  } catch (e) {
    const err = e instanceof Error ? e.message : String(e);
    res.status(400).json(
      body.device_ids.map((id) => ({ device_id: id, ok: false, error: `bad params_json: ${err}` })),
    );
    return;
  }

  const nowIso = new Date().toISOString();
  const expiresAtIso = new Date(Date.now() + (body.expires_in_sec ?? 3600) * 1000).toISOString();

  const settled = await Promise.allSettled(
    body.device_ids.map(async (deviceId) => {
      const messageId = crypto.randomUUID();
      await applyAction(FOUNDRY, "issue-command", {
        message_id: messageId,
        device_id: deviceId,
        mission_id: "none",
        verb: body.verb,
        params_json: body.params_json,
        priority: body.priority,
        status: "PENDING",
        issued_at: nowIso,
        expires_at: expiresAtIso,
        acked_at: "none",
        completed_at: "none",
        supersedes: "none",
      });
      return { deviceId, messageId };
    }),
  );

  const results: IssueCommandResult[] = settled.map((s, i) => {
    const deviceId = body.device_ids[i];
    if (s.status === "fulfilled") {
      return { device_id: deviceId, ok: true, message_id: s.value.messageId };
    }
    return {
      device_id: deviceId,
      ok: false,
      error: s.reason instanceof Error ? s.reason.message : String(s.reason),
    };
  });
  res.json(results);
});

app.listen(PORT, () => {
  console.log(`[bff] listening on http://localhost:${PORT}  (mock=${MOCK_MODE})`);
  console.log(`[bff] CORS allow-origin: ${ORIGIN}`);
  if (!MOCK_MODE) {
    console.log(`[bff] Foundry stack: ${FOUNDRY.stackUrl}`);
    console.log(`[bff] Foundry ontology: ${FOUNDRY.ontology}`);
  }
});
