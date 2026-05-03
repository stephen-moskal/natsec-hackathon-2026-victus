/** Thin Foundry REST wrapper — mirrors the request shapes used by
 *  edge/src/victus_edge/comms/foundry_client.py exactly. Keep this file the
 *  source of truth for all Foundry interactions.
 */

import { fetch } from "undici";

export type FoundryConfig = {
  stackUrl: string;          // https://victus.usw-23.palantirfoundry.com (no trailing slash)
  ontology: string;          // ontology API name OR RID
  token: string;             // bearer
};

export type WhereClause =
  | { type: "eq"; field: string; value: string | number | boolean }
  | { type: "and"; value: WhereClause[] }
  | { type: "or"; value: WhereClause[] };

export type OrderBy = {
  fields: { field: string; direction: "asc" | "desc" }[];
};

// ── Search Objects ─────────────────────────────────────────────────────────

export async function searchObjects(
  cfg: FoundryConfig,
  objectType: string,
  opts: { where?: WhereClause; orderBy?: OrderBy; pageSize?: number } = {},
): Promise<Record<string, unknown>[]> {
  const url =
    `${cfg.stackUrl}/api/v2/ontologies/${cfg.ontology}/objects/${objectType}/search`;
  const body: Record<string, unknown> = { pageSize: opts.pageSize ?? 50 };
  if (opts.where) body.where = opts.where;
  if (opts.orderBy) body.orderBy = opts.orderBy;

  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${cfg.token}`,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Foundry searchObjects(${objectType}) ${res.status}: ${text.slice(0, 500)}`);
  }
  const json = (await res.json()) as { data?: Record<string, unknown>[] };
  return json.data ?? [];
}

// ── Last FrameThumbnail from Foundry cold storage ─────────────────────────
// Fallback when the Jetson frame server is unreachable. Queries raw_telemetry
// cold dataset for the most recent FrameThumbnail event for this device,
// decodes the base64 payload, and returns raw JPEG bytes (or null).

export async function getLastFoundryFrame(
  cfg: FoundryConfig,
  deviceId: string,
  rawTelemetryRid: string,
): Promise<Buffer | null> {
  const sender = `drone-${deviceId}`;
  const sql =
    `SELECT payload_json FROM \`${rawTelemetryRid}\`` +
    ` WHERE event = 'FrameThumbnail' AND sender = '${sender}'` +
    ` ORDER BY issued_at DESC LIMIT 1`;
  try {
    const res = await fetch(
      `${cfg.stackUrl}/api/v2/sqlQueries/execute?preview=true`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${cfg.token}` },
        body: JSON.stringify({ query: sql }),
      },
    );
    if (!res.ok) return null;
    const data = (await res.json()) as { rows?: unknown[][] };
    const raw = data.rows?.[0]?.[0];
    if (!raw || typeof raw !== "string") return null;
    const payload = JSON.parse(raw) as { b64?: string };
    if (!payload.b64) return null;
    return Buffer.from(payload.b64, "base64");
  } catch {
    return null;
  }
}

// ── Action Apply ───────────────────────────────────────────────────────────

export async function applyAction(
  cfg: FoundryConfig,
  actionApiName: string,
  parameters: Record<string, unknown>,
): Promise<{ operationId: string }> {
  const url =
    `${cfg.stackUrl}/api/v2/ontologies/${cfg.ontology}/actions/${actionApiName}/apply`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${cfg.token}`,
    },
    body: JSON.stringify({ parameters }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Foundry applyAction(${actionApiName}) ${res.status}: ${text.slice(0, 500)}`);
  }
  const json = (await res.json()) as { operationId?: string };
  return { operationId: json.operationId ?? "" };
}

// ── Health probe ───────────────────────────────────────────────────────────

export async function pingFoundry(cfg: FoundryConfig): Promise<boolean> {
  try {
    // Cheap call: just probe the ontology endpoint.
    const res = await fetch(`${cfg.stackUrl}/api/v2/ontologies/${cfg.ontology}`, {
      method: "GET",
      headers: { Authorization: `Bearer ${cfg.token}` },
    });
    return res.status < 500; // 200 is healthy; 401/403 still mean "Foundry reachable"
  } catch {
    return false;
  }
}

// ── JWT expiry decode ──────────────────────────────────────────────────────
// Personal Foundry tokens are JWTs with an `exp` claim (epoch seconds).

export function decodeTokenExpiry(token: string): { exp: number | null; iso: string | null } {
  try {
    const parts = token.split(".");
    if (parts.length < 2) return { exp: null, iso: null };
    const payload = JSON.parse(
      Buffer.from(parts[1].replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf-8"),
    ) as { exp?: number };
    if (typeof payload.exp !== "number") return { exp: null, iso: null };
    return {
      exp: payload.exp,
      iso: new Date(payload.exp * 1000).toISOString(),
    };
  } catch {
    return { exp: null, iso: null };
  }
}
