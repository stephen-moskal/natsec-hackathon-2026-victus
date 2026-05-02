# Jetson bring-up — bidirectional API bridge test

End-to-end test: edge process on the Jetson talks to a local Foundry stub on the Mac over the USB-C network. Outbound (telemetry POST) and inbound (command poll + ACK) are both proven before we depend on real Foundry.

**Network state** (already verified):
- Mac USB-C interface: `en11`, IP `192.168.55.100`
- Jetson default USB-C IP: `192.168.55.1`
- ping latency Mac→Jetson: ~1 ms

## 1. SSH to the Jetson (Mac side)

The Jetson Orin DevKit ships with `sshd` enabled and the user account you created during OOBE. Try it from the Mac:

```bash
ssh <jetson-user>@192.168.55.1
```

Replace `<jetson-user>` with whatever you set up during the Jetson's first-boot flow (often `nvidia`, `ubuntu`, or your name). On first connect you'll see a host-key fingerprint prompt — accept it.

If SSH fails:
- `Connection refused` → SSH server isn't running. Plug in HDMI + keyboard and run `sudo systemctl enable --now ssh` on the Jetson, or check `sudo systemctl status ssh`.
- `Permission denied` → wrong username, or password auth disabled. Use the username from OOBE and the password you set.
- `No route to host` → USB-C link dropped. Re-plug the cable and re-run `ping 192.168.55.1` on the Mac.

Once you're in, sanity-check Python:

```bash
python3 --version    # need 3.10+
which pip3
```

If Python is older than 3.10, install via apt: `sudo apt install python3.10 python3.10-venv python3-pip`.

## 2. Push the edge code to the Jetson (Mac side)

From the repo root on the Mac:

```bash
JETSON=<jetson-user>@192.168.55.1
ssh $JETSON 'mkdir -p ~/victus'
rsync -avz --delete \
  --exclude '.venv' --exclude '__pycache__' --exclude '.pytest_cache' \
  edge/ shared/ \
  $JETSON:~/victus/
```

The edge code only needs `edge/` (its source) and `shared/` (the protocol JSON schemas it loads at import).

## 3. Install dependencies (Jetson side)

```bash
ssh $JETSON
cd ~/victus/edge
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

This installs `httpx`, `jsonschema`, `structlog`, `tenacity`, etc. On first run the Jetson may pull a few hundred MB of wheels.

Verify:

```bash
python3 -c "from victus_edge.comms import protocol, foundry_client, auth; print('imports ok, proto', protocol.PROTOCOL_VERSION)"
# expected: imports ok, proto 0.2.0
```

## 4. Edge `.env` on the Jetson

Still inside the SSH session:

```bash
cat > ~/victus/edge/.env <<'EOF'
VICTUS_DRONE_ID=uav-01
FOUNDRY_LISTENER_URL=http://192.168.55.100:8080/listener/telemetry
FOUNDRY_FUNCTIONS_URL=http://192.168.55.100:8080/functions
FOUNDRY_AUTH_MODE=STATIC
FOUNDRY_TOKEN=stub-token
COMMAND_POLL_INTERVAL_S=2.0
POSITION_EMIT_INTERVAL_S=5.0
VICTUS_LOG_LEVEL=INFO
EOF
```

The stub accepts any bearer; `stub-token` is just a placeholder. We'll swap to real Foundry creds later.

## 5. Run the test (two terminals on the Mac, one SSH session to Jetson)

### Terminal 1 — Mac, start the stub

```bash
cd /Users/smoskal/Documents/Foundry/natsec-hackathon-2026-victus
python3 tools/foundry_stub.py --port 8080
```

You should see:
```
[stub] listening on http://0.0.0.0:8080
[stub] from Jetson use http://192.168.55.100:8080
```

### Terminal 2 — Mac, watch state and inject a command

Confirm the Jetson can reach the stub:

```bash
ssh $JETSON 'curl -s http://192.168.55.100:8080/healthz'
# expected: {"ok": true, "protocol_version": "0.2.0"}
```

(Keep this terminal open — we'll use it later to inject commands.)

### Terminal 3 — Jetson SSH, run the edge

```bash
ssh $JETSON
cd ~/victus/edge
source .venv/bin/activate
set -a && source .env && set +a    # load env vars into the shell
python -m victus_edge.main
```

Expected output within ~5 seconds:
```
... edge_starting drone_id=uav-01 auth_mode=STATIC ...
```
And every 5 s, the stub (Terminal 1) should print:
```
[telemetry] sender=drone-uav-01 event=Position mid=...
```

That proves **outbound telemetry works**.

### Terminal 2 — Inject a command

```bash
curl -s -X POST http://127.0.0.1:8080/admin/inject_command \
  -H "Content-Type: application/json" \
  -d '{"drone_id":"uav-01","verb":"HOLD"}'
```

Within ~2 s (the edge's poll interval), Terminal 3 (edge stdout) should print:
```
... command_received message_id=<uuid> verb=HOLD params={} ...
```

And the stub (Terminal 1) should print:
```
[telemetry] sender=drone-uav-01 event=CommandAck mid=...
```

That proves **inbound commands work** AND **the edge ACKs them via the same telemetry channel**.

### Verify state

```bash
curl -s http://127.0.0.1:8080/admin/state | python3 -m json.tool
```

Expect to see:
- `telemetry_count`: > 0 (and growing)
- `pending_by_drone.uav-01`: contains the command's message_id
- `served_counts.uav-01`: 1 (the command was polled exactly once)
- Recent telemetry should include the `CommandAck` event

## 6. What "success" looks like

You've validated the bridge if:
- Edge process on Jetson posts Position events every 5 s, visible in stub logs.
- Operator-injected command shows up on the edge stdout within 2 s.
- Edge ACKs the command — visible as a `CommandAck` event in the stub's telemetry log.

At that point, swapping to real Foundry is just changing three env vars in `.env` (`FOUNDRY_LISTENER_URL`, `FOUNDRY_FUNCTIONS_URL`, `FOUNDRY_TOKEN`) once the Foundry-side UI work in [foundry/WORKSHOP_RUNBOOK.md](../foundry/WORKSHOP_RUNBOOK.md) is done.

## Common stumbles

- **Edge can't reach the stub**: from the Jetson, `curl -v http://192.168.55.100:8080/healthz`. If it hangs, the Mac may have a firewall (System Settings → Network → Firewall → allow Python). USB-C link instability also looks like this — re-seat the cable.
- **`ModuleNotFoundError: jsonschema`**: you forgot `source .venv/bin/activate`.
- **Imports fail with `FileNotFoundError: shared/protocol/schemas/...`**: you only rsync'd `edge/`, not `shared/`. Re-run the rsync from step 2 with both paths.
- **Edge crashes with `required env var not set: FOUNDRY_TOKEN`**: the `set -a && source .env && set +a` line didn't run. Re-source.
- **Position events arrive but commands don't**: check that the inject curl returned `{"ok": true, ...}` and that the `drone_id` you injected matches `VICTUS_DRONE_ID` exactly.
