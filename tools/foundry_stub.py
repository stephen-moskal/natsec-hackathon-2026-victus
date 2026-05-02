"""Local Foundry stub for end-to-end testing of the VICTUS edge.

Stdlib only (no pip install). Mimics the two real Foundry REST APIs that
the edge talks to:

  POST /api/v2/highScale/streams/datasets/{datasetRid}/streams/master/publishRecords
       (Streams V2 publishRecords — inbound telemetry)

  POST /api/v2/ontologies/{ontology}/objects/{objectType}/search
       (Ontology Search Objects — outbound commands queried by the edge)

Plus admin endpoints for the operator (you):

  POST /admin/inject_command   queue a command for a drone to pick up
  GET  /admin/state            what's been received and what's pending
  GET  /healthz                liveness

Run on Mac so the Jetson can reach via the USB-C network:

    python3 tools/foundry_stub.py --host 0.0.0.0 --port 8080

From the Jetson:
    curl http://192.168.55.100:8080/healthz

Auth: any bearer token is accepted. Path params (dataset RID, ontology, object
type) are also accepted as any value — the stub doesn't validate them. The
goal is to prove the wire shape, not test auth or routing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


PROTOCOL_VERSION = "0.2.0"

# Match the Streams V2 path with any datasetRid + branch.
PUBLISH_RECORDS_RE = re.compile(
    r"^/api/v2/highScale/streams/datasets/(?P<dataset>[^/]+)/streams/(?P<branch>[^/]+)/publishRecords/?$"
)
# Match the Ontology Search Objects path with any ontology + objectType.
SEARCH_OBJECTS_RE = re.compile(
    r"^/api/v2/ontologies/(?P<ontology>[^/]+)/objects/(?P<object_type>[^/]+)/search/?$"
)


class State:
    """In-memory state. Threadsafe via a single lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.telemetry_records: list[dict[str, Any]] = []   # flat records as published
        # device_id -> list of pending Command-shaped objects (FIFO)
        self.pending: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def record_telemetry_records(self, records: list[dict[str, Any]]) -> None:
        with self._lock:
            self.telemetry_records.extend(records)

    def queue_command(self, obj: dict[str, Any]) -> None:
        with self._lock:
            self.pending[obj["deviceId"]].append(obj)

    def search_pending(self, drone_id: str) -> list[dict[str, Any]]:
        with self._lock:
            # Return all PENDING for this drone, ordered by messageId ascending.
            return sorted(
                [c for c in self.pending.get(drone_id, []) if c.get("status") == "PENDING"],
                key=lambda c: c["messageId"],
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "telemetry_count": len(self.telemetry_records),
                "telemetry_recent": self.telemetry_records[-10:],
                "pending_by_drone": {
                    d: [{"messageId": c["messageId"], "verb": c["verb"], "status": c["status"]} for c in q]
                    for d, q in self.pending.items()
                },
            }


STATE = State()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_command_object(body: dict[str, Any]) -> dict[str, Any]:
    """Take a loose admin-injected payload and assemble a Command-shaped object.

    Keys match Foundry's auto-converted camelCase property API names so the
    stub mirrors the shape of real Search Objects responses exactly.
    """
    drone_id = body["drone_id"]
    verb = body.get("verb", "HOLD")
    params = body.get("params", {})
    priority = body.get("priority", "ROUTINE")
    expires_in_s = body.get("expires_in_s", 3600)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in_s)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return {
        "messageId": str(uuid.uuid4()),
        "deviceId": drone_id,
        "missionId": "none",
        "verb": verb,
        "paramsJson": json.dumps(params),
        "priority": priority,
        "status": "PENDING",
        "issuedAt": _now_iso(),
        "expiresAt": expires_at,
        "ackedAt": "none",
        "completedAt": "none",
        "supersedes": "none",
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args) -> None:
        sys.stderr.write(f"[{_now_iso()}] {self.address_string()} - {fmt % args}\n")

    def _read_json(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(n) if n else b"{}"
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"error": f"invalid json: {e}"})
            raise

    def _send_json(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    # ----- Routes -----

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/admin/state":
            self._send_json(200, STATE.snapshot())
            return
        if self.path == "/healthz":
            self._send_json(200, {"ok": True, "protocol_version": PROTOCOL_VERSION})
            return
        self._send_json(404, {"error": f"unknown path {self.path}"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            body = self._read_json()
        except Exception:
            return

        # Admin: queue a command for a drone to pick up on next search.
        if self.path == "/admin/inject_command":
            try:
                obj = _build_command_object(body)
            except KeyError as e:
                self._send_json(400, {"error": f"missing field {e}"})
                return
            STATE.queue_command(obj)
            sys.stdout.write(
                f"[inject ] drone={obj['device_id']} verb={obj['verb']} mid={obj['message_id'][:8]}...\n"
            )
            sys.stdout.flush()
            self._send_json(200, {"ok": True, "message_id": obj["message_id"]})
            return

        # Streams V2: publishRecords.
        m = PUBLISH_RECORDS_RE.match(self.path)
        if m:
            records = body.get("records", [])
            if not isinstance(records, list):
                self._send_json(400, {"error": "records must be an array"})
                return
            STATE.record_telemetry_records(records)
            for rec in records:
                sys.stdout.write(
                    f"[telemetry] sender={rec.get('sender', '?')} "
                    f"event={rec.get('event', '?')} "
                    f"mid={(rec.get('message_id', '') or '')[:8]}...\n"
                )
            sys.stdout.flush()
            self._send_json(200, {"type": "publishRecordsResponse", "recordsPublished": len(records)})
            return

        # Ontology Search Objects.
        m = SEARCH_OBJECTS_RE.match(self.path)
        if m:
            where = body.get("where", {})
            # Real Foundry uses camelCase property API names; tolerate both for safety.
            drone_id = self._extract_eq(where, "deviceId") or self._extract_eq(where, "device_id")
            if not drone_id:
                self._send_json(400, {"error": "could not extract deviceId from where clause"})
                return
            results = STATE.search_pending(drone_id)
            self._send_json(200, {"data": results, "totalCount": str(len(results))})
            return

        self._send_json(404, {"error": f"unknown path {self.path}"})

    @staticmethod
    def _extract_eq(where_clause: dict[str, Any], field: str) -> str | None:
        """Walk an Ontology Search 'where' tree and return the equality value for `field`."""
        if not isinstance(where_clause, dict):
            return None
        if where_clause.get("type") == "eq" and where_clause.get("field") == field:
            return where_clause.get("value")
        if where_clause.get("type") in ("and", "or"):
            for child in where_clause.get("value", []):
                v = Handler._extract_eq(child, field)
                if v is not None:
                    return v
        return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[stub] listening on http://{args.host}:{args.port}")
    print(f"[stub] from Jetson use http://192.168.55.100:{args.port}")
    print(f"[stub] endpoints (Foundry-shaped):")
    print(f"          POST /api/v2/highScale/streams/datasets/<rid>/streams/<branch>/publishRecords")
    print(f"          POST /api/v2/ontologies/<ontology>/objects/<object_type>/search")
    print(f"[stub] admin endpoints:")
    print(f"          POST /admin/inject_command   body: {{drone_id, verb?, params?, priority?, expires_in_s?}}")
    print(f"          GET  /admin/state")
    print(f"          GET  /healthz")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[stub] shutting down")
        srv.server_close()


if __name__ == "__main__":
    main()
