"""Local Foundry stub for end-to-end testing of the VICTUS edge.

Stdlib only (no pip install). Mimics two Foundry endpoints the edge talks to:

  POST /listener/telemetry          (HTTPS Listener inbound)
  POST /functions/pollCommands/execute  (TS v2 query function)

Plus admin endpoints for the operator (you):

  POST /admin/inject_command        (queue a command for a drone to pick up)
  GET  /admin/state                 (what's been received and what's pending)

Run on Mac so the Jetson can reach via the USB-C network:

    python3 tools/foundry_stub.py --host 0.0.0.0 --port 8080

From the Jetson:
    curl http://192.168.55.100:8080/admin/state
should return JSON. From the Mac, that same URL works too.

Auth: any bearer token is accepted (set FOUNDRY_TOKEN to anything in the
edge .env). The stub doesn't validate tokens; the goal is to prove the wire
shape, not to test auth.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


PROTOCOL_VERSION = "0.2.0"


class State:
    """In-memory state. Threadsafe via a single lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.telemetry: list[dict[str, Any]] = []
        # device_id -> list of pending command envelopes (FIFO)
        self.pending: dict[str, list[dict[str, Any]]] = defaultdict(list)
        # device_id -> set of message_ids already returned (so we can serve cursor logic)
        self.served: dict[str, set[str]] = defaultdict(set)

    def record_telemetry(self, env: dict[str, Any]) -> None:
        with self._lock:
            self.telemetry.append(env)

    def queue_command(self, env: dict[str, Any]) -> None:
        with self._lock:
            drone_id = env["payload"]["drone_id"]
            self.pending[drone_id].append(env)

    def poll(self, drone_id: str, since_message_id: str | None) -> dict[str, Any]:
        with self._lock:
            queue = self.pending.get(drone_id, [])
            # Serve everything not yet served, optionally filtered by cursor.
            out: list[dict[str, Any]] = []
            for env in queue:
                mid = env["message_id"]
                if mid in self.served[drone_id]:
                    continue
                if since_message_id and mid <= since_message_id:
                    continue
                out.append(env)
                self.served[drone_id].add(mid)
            cursor = out[-1]["message_id"] if out else since_message_id
            return {"commands": out, "cursor": cursor}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "telemetry_count": len(self.telemetry),
                "telemetry_recent": self.telemetry[-10:],
                "pending_by_drone": {
                    d: [e["message_id"] for e in q] for d, q in self.pending.items()
                },
                "served_counts": {d: len(s) for d, s in self.served.items()},
            }


STATE = State()


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_command_envelope(body: dict[str, Any]) -> dict[str, Any]:
    """Take a loose admin-injected payload and assemble a valid command envelope."""
    drone_id = body["drone_id"]
    verb = body.get("verb", "HOLD")
    params = body.get("params", {})
    priority = body.get("priority", "ROUTINE")
    expires_in_s = body.get("expires_in_s", 3600)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in_s)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return {
        "protocol_version": PROTOCOL_VERSION,
        "message_id": str(uuid.uuid4()),
        "issued_at": _now_iso(),
        "sender": "foundry-stub",
        "kind": "command",
        "payload": {
            "drone_id": drone_id,
            "verb": verb,
            "priority": priority,
            "expires_at": expires_at,
            "params": params,
        },
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

        if self.path == "/listener/telemetry":
            event = body.get("payload", {}).get("event", "?")
            sender = body.get("sender", "?")
            mid = body.get("message_id", "?")
            STATE.record_telemetry(body)
            sys.stdout.write(
                f"[telemetry] sender={sender} event={event} mid={mid[:8]}...\n"
            )
            sys.stdout.flush()
            self._send_json(200, {"ok": True})
            return

        if self.path == "/functions/pollCommands/execute":
            params = body.get("parameters", {})
            drone_id = params.get("droneId")
            since = params.get("sinceMessageId")
            if not drone_id:
                self._send_json(400, {"error": "missing parameters.droneId"})
                return
            result = STATE.poll(drone_id, since)
            self._send_json(200, {"value": result})
            return

        if self.path == "/admin/inject_command":
            try:
                env = _build_command_envelope(body)
            except KeyError as e:
                self._send_json(400, {"error": f"missing field {e}"})
                return
            STATE.queue_command(env)
            sys.stdout.write(
                f"[inject ] drone={env['payload']['drone_id']} verb={env['payload']['verb']} "
                f"mid={env['message_id'][:8]}...\n"
            )
            sys.stdout.flush()
            self._send_json(200, {"ok": True, "message_id": env["message_id"]})
            return

        self._send_json(404, {"error": f"unknown path {self.path}"})


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8080)
    args = p.parse_args()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[stub] listening on http://{args.host}:{args.port}")
    print(f"[stub] from Jetson use http://192.168.55.100:{args.port}")
    print(f"[stub] endpoints:")
    print(f"          POST /listener/telemetry")
    print(f"          POST /functions/pollCommands/execute")
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
