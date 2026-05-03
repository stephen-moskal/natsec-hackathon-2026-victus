import express, { type Request, type Response } from "express";
import cors from "cors";
import dotenv from "dotenv";
import { fetch as undiciFetch } from "undici";
import type {
  Drone,
  Command,
  CommandAck,
  Mission,
  FoundryHealth,
  IssueCommandRequest,
  IssueCommandResult,
  CreateMissionRequest,
  AssignMissionRequest,
  AssignMissionResult,
} from "./types.js";
import {
  type FoundryConfig,
  searchObjects,
  applyAction,
  pingFoundry,
  decodeTokenExpiry,
} from "./foundry.js";
import { droneFromFoundry, commandFromFoundry, commandAckFromFoundry, missionFromFoundry } from "./camelcase.js";

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
    { drone_id: "uav-01", callsign: "ALPHA", protocol_version: "0.2.0", last_seen_at: nowIso, lat: 37.7955, lon: -122.3937, alt_m: 100, heading_deg: 90, speed_mps: 0, battery_pct: 95, state: "NOMINAL", current_mission_id: "none", link_status: "ONLINE" },
    { drone_id: "uav-02", callsign: "BRAVO", protocol_version: "0.2.0", last_seen_at: nowIso, lat: 37.7749, lon: -122.4194, alt_m: 120, heading_deg: 180, speed_mps: 0, battery_pct: 88, state: "NOMINAL", current_mission_id: "none", link_status: "ONLINE" },
    { drone_id: "uav-03", callsign: "CHARLIE", protocol_version: "0.2.0", last_seen_at: nowIso, lat: 37.7614, lon: -122.4862, alt_m: 110, heading_deg: 270, speed_mps: 0, battery_pct: 72, state: "NOMINAL", current_mission_id: "none", link_status: "ONLINE" },
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
    const objs = await searchObjects(FOUNDRY, "drone", {
      orderBy: { fields: [{ field: "droneId", direction: "asc" }] },
      pageSize: 100,
    });
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
    // Fetch commands and, in parallel, any CommandAck records for the same device.
    // The command_ack object type may not yet be deployed (Phase 4b); if the
    // search fails we fall back gracefully to raw PENDING status.
    const [cmdObjs, ackObjs] = await Promise.all([
      searchObjects(FOUNDRY, "command", {
        where: { type: "eq", field: "deviceId", value: deviceId },
        orderBy: { fields: [{ field: "issuedAt", direction: "desc" }] },
        pageSize: limit,
      }),
      searchObjects(FOUNDRY, "commandAck", {
        where: { type: "eq", field: "deviceId", value: deviceId },
        pageSize: 200,
      }).catch(() => [] as Record<string, unknown>[]),
    ]);

    // Build a lookup: command_id → CommandAck (most-recent result wins).
    const ackMap = new Map<string, CommandAck>();
    for (const obj of ackObjs) {
      const ack = commandAckFromFoundry(obj);
      if (ack.command_id && !ackMap.has(ack.command_id)) {
        ackMap.set(ack.command_id, ack);
      }
    }

    // Derive effective status from the ACK result.
    const RESULT_TO_STATUS: Record<string, string> = {
      WILCO:   "ACKED",
      ROGER:   "ACKED",
      STANDBY: "ACKED",
      UNABLE:  "REJECTED",
      EXPIRED: "EXPIRED",
    };

    const commands: Command[] = cmdObjs.map((obj) => {
      const cmd = commandFromFoundry(obj);
      const ack = ackMap.get(cmd.message_id);
      if (ack) {
        cmd.status   = RESULT_TO_STATUS[ack.result] ?? cmd.status;
        cmd.acked_at = ack.acked_at;
      }
      return cmd;
    });

    res.json(commands);
  } catch (e) {
    console.error("[bff] /api/commands error:", e);
    res.status(502).json({ error: e instanceof Error ? e.message : String(e) });
  }
});

// ── Missions (Phase 3) ─────────────────────────────────────────────────────
//
// GET  /api/missions                   list all missions
// POST /api/missions                   create a mission via the create-mission action
// POST /api/assign-mission             fan-out N ASSIGN_MISSION commands to drones
//
// Mission rows live in the missions_v1 dataset (pzqmccug.mission). The hero
// field is system_prompt — it forms the top of the on-board LLM's system
// prompt when delivered via the ASSIGN_MISSION command.

const SYSTEM_PROMPT_MAX_BYTES = 8192;
const VALID_PRIORITIES = new Set(["ROUTINE", "PRIORITY", "IMMEDIATE", "FLASH"]);

app.get("/api/missions", async (_req: Request, res: Response) => {
  if (MOCK_MODE) {
    res.json([]);
    return;
  }
  try {
    const objs = await searchObjects(FOUNDRY, "mission", {
      orderBy: { fields: [{ field: "createdAt", direction: "desc" }] },
      pageSize: 100,
    });
    const missions: Mission[] = objs.map(missionFromFoundry);
    res.json(missions);
  } catch (e) {
    console.error("[bff] /api/missions error:", e);
    res.status(502).json({ error: e instanceof Error ? e.message : String(e) });
  }
});

app.post("/api/missions", async (req: Request, res: Response) => {
  const body = req.body as CreateMissionRequest;
  if (!body || !body.name || !body.system_prompt) {
    res.status(400).json({ error: "name and system_prompt are required" });
    return;
  }
  if (Buffer.byteLength(body.system_prompt, "utf-8") > SYSTEM_PROMPT_MAX_BYTES) {
    res.status(400).json({ error: `system_prompt exceeds ${SYSTEM_PROMPT_MAX_BYTES} bytes` });
    return;
  }
  const priority = body.priority ?? "ROUTINE";
  if (!VALID_PRIORITIES.has(priority)) {
    res.status(400).json({ error: `priority must be one of ${[...VALID_PRIORITIES].join(", ")}` });
    return;
  }

  const missionId = crypto.randomUUID();
  const nowIso = new Date().toISOString();
  const parameters = {
    mission_id: missionId,
    name: body.name,
    description: body.description || "none",
    system_prompt: body.system_prompt,
    objectives: body.objectives || "none",
    target_specs: body.target_specs || "none",
    area_geo_json: body.area_geo_json || "none",
    priority,
    roe_profile: body.roe_profile || "roe-default",
    active: "false",
    assigned_device_ids: "none",
    created_at: nowIso,
    updated_at: nowIso,
  };

  if (MOCK_MODE) {
    res.json(parameters);
    return;
  }

  try {
    await applyAction(FOUNDRY, "create-mission", parameters);
    // Echo the created row shape back for the UI to optimistically render.
    const mission: Mission = {
      mission_id: missionId,
      name: parameters.name,
      description: parameters.description,
      system_prompt: parameters.system_prompt,
      objectives: parameters.objectives,
      target_specs: parameters.target_specs,
      area_geo_json: parameters.area_geo_json,
      priority: parameters.priority,
      roe_profile: parameters.roe_profile,
      active: parameters.active,
      assigned_device_ids: parameters.assigned_device_ids,
      created_at: parameters.created_at,
      updated_at: parameters.updated_at,
    };
    res.json(mission);
  } catch (e) {
    console.error("[bff] POST /api/missions error:", e);
    res.status(502).json({ error: e instanceof Error ? e.message : String(e) });
  }
});

app.post("/api/assign-mission", async (req: Request, res: Response<AssignMissionResult[]>) => {
  const body = req.body as AssignMissionRequest;
  if (!body || !body.mission_id || !Array.isArray(body.device_ids) || body.device_ids.length === 0) {
    res.status(400).json([]);
    return;
  }

  if (MOCK_MODE) {
    res.json(
      body.device_ids.map((id) => ({
        device_id: id,
        ok: true,
        message_id: crypto.randomUUID(),
      })),
    );
    return;
  }

  // 1. Look up the mission so we can pack name/system_prompt into params_json.
  let mission: Mission;
  try {
    const objs = await searchObjects(FOUNDRY, "mission", {
      where: { type: "eq", field: "missionId", value: body.mission_id },
      pageSize: 1,
    });
    if (objs.length === 0) {
      res.status(404).json(
        body.device_ids.map((id) => ({
          device_id: id,
          ok: false,
          error: `mission ${body.mission_id} not found`,
        })),
      );
      return;
    }
    mission = missionFromFoundry(objs[0]);
  } catch (e) {
    const err = e instanceof Error ? e.message : String(e);
    res.status(502).json(
      body.device_ids.map((id) => ({ device_id: id, ok: false, error: `mission lookup failed: ${err}` })),
    );
    return;
  }

  // 2. Build the ASSIGN_MISSION params payload. Drop "none" sentinels so the
  //    drone-side LLM doesn't see noise.
  const params: Record<string, string> = {
    mission_id: mission.mission_id,
    name: mission.name,
    system_prompt: mission.system_prompt,
  };
  if (mission.objectives && mission.objectives !== "none") params.objectives = mission.objectives;
  if (mission.target_specs && mission.target_specs !== "none") params.target_specs = mission.target_specs;
  if (mission.area_geo_json && mission.area_geo_json !== "none") params.area_geo_json = mission.area_geo_json;
  if (mission.roe_profile && mission.roe_profile !== "none") params.roe_profile = mission.roe_profile;

  const paramsJson = JSON.stringify(params);
  const nowIso = new Date().toISOString();
  const expiresAtIso = new Date(Date.now() + (body.expires_in_sec ?? 3600) * 1000).toISOString();

  // 3. Fan-out one issue-command per drone. Partial failure is surfaced
  //    per-device; UI can retry the failed ones.
  const settled = await Promise.allSettled(
    body.device_ids.map(async (deviceId) => {
      const messageId = crypto.randomUUID();
      await applyAction(FOUNDRY, "issue-command", {
        message_id: messageId,
        device_id: deviceId,
        mission_id: mission.mission_id,
        verb: "ASSIGN_MISSION",
        params_json: paramsJson,
        priority: mission.priority || "ROUTINE",
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

  const results: AssignMissionResult[] = settled.map((s, i) => {
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

// ── Video frame proxy (Phase 4c live path) ─────────────────────────────────
//
// GET /api/frame/:deviceId
//
// Proxies directly to the edge's frame server (port 8888) on the Jetson.
// Bypasses the Foundry batch pipeline entirely for near-real-time display.
// The edge simultaneously publishes FrameThumbnail events to raw_telemetry
// so frames are also captured and stored in Foundry for historical analysis.
//
// JETSON_HOST env var controls the target (default: 192.168.55.1 USB-C tether).

const JETSON_HOST = (process.env.JETSON_HOST ?? "192.168.55.1").replace(/\/$/, "");
const FRAME_SERVER_PORT = Number(process.env.JETSON_FRAME_PORT ?? 8888);

// Only devices listed here have a live frame server. Others return 404 immediately
// so BRAVO/CHARLIE show "NO VIDEO" rather than serving the wrong camera.
const DEVICE_HOSTS: Record<string, string> = {
  "uav-01": JETSON_HOST,
};

// In-memory frame cache — last successfully fetched JPEG per device.
// When the Jetson is unreachable (USB-C unplugged etc.) we serve the cached
// frame instantly rather than blocking on a slow Foundry SQL query.
const frameCache = new Map<string, Buffer>();

app.get("/api/frame/:deviceId", async (req: Request, res: Response) => {
  const deviceId = String(req.params.deviceId);
  const host = DEVICE_HOSTS[deviceId];

  if (!host) {
    res.status(404).send("No frame server configured for this device");
    return;
  }

  // Primary: live Jetson frame server (~5ms when USB-C tether is up).
  try {
    const upstream = await undiciFetch(
      `http://${host}:${FRAME_SERVER_PORT}/frame`,
      { signal: AbortSignal.timeout(2000) },
    );
    if (upstream.ok) {
      const buf = Buffer.from(await upstream.arrayBuffer());
      frameCache.set(deviceId, buf);          // keep a hot copy for fallback
      res.set("Content-Type", "image/jpeg");
      res.set("Cache-Control", "no-store");
      res.set("X-Frame-Source", "live");
      res.send(buf);
      return;
    }
  } catch {
    // Jetson unreachable — serve last cached frame immediately.
  }

  // Fallback: last frame seen this session (in-memory, instant).
  const cached = frameCache.get(deviceId);
  if (cached) {
    res.set("Content-Type", "image/jpeg");
    res.set("Cache-Control", "no-store");
    res.set("X-Frame-Source", "cached");
    res.send(cached);
    return;
  }

  res.status(503).send("No frame available");
});

app.listen(PORT, () => {
  console.log(`[bff] listening on http://localhost:${PORT}  (mock=${MOCK_MODE})`);
  console.log(`[bff] CORS allow-origin: ${ORIGIN}`);
  if (!MOCK_MODE) {
    console.log(`[bff] Foundry stack: ${FOUNDRY.stackUrl}`);
    console.log(`[bff] Foundry ontology: ${FOUNDRY.ontology}`);
  }
});
