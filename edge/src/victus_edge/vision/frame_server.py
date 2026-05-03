"""Webcam capture + dual-path frame distribution.

Two responsibilities run concurrently as asyncio tasks:

1. **HTTP frame server** (port 8888) — serves the latest JPEG directly via a
   tiny asyncio HTTP server. The BFF proxies /api/frame/:deviceId here for
   near-real-time display (sub-second latency, bypasses Foundry batch pipeline).

2. **Foundry publisher** — encodes each frame as base64 JPEG and publishes a
   FrameThumbnail telemetry event to raw_telemetry via the existing
   post_telemetry path. Frames are then stored in Foundry for historical
   analysis and will be projected by the last_frame transform (Phase 4c).

Usage:
    from victus_edge.vision.frame_server import run_frame_server
    asyncio.create_task(run_frame_server(client, cfg))
"""

import asyncio
import base64
import io
import logging
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

# Lazy import so the module loads even if OpenCV isn't installed.
try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False
    log.warning("cv2_not_available", msg="OpenCV not installed — frame server disabled")

FRAME_SERVER_PORT = 8888
CAPTURE_INTERVAL_S = 1.0      # capture a new frame every second
FOUNDRY_EMIT_INTERVAL_S = 5.0 # publish to Foundry every 5s (don't flood raw_telemetry)
JPEG_QUALITY = 60
FRAME_WIDTH = 640
FRAME_HEIGHT = 360


class _FrameStore:
    """Thread-safe (asyncio-safe) shared latest-frame buffer."""
    def __init__(self) -> None:
        self._jpeg: Optional[bytes] = None
        self._event = asyncio.Event()

    def put(self, jpeg: bytes) -> None:
        self._jpeg = jpeg
        self._event.set()

    def get(self) -> Optional[bytes]:
        return self._jpeg

    async def wait_for_frame(self) -> bytes:
        await self._event.wait()
        return self._jpeg  # type: ignore[return-value]


async def _capture_loop(store: _FrameStore, cfg) -> None:
    """Continuously read frames from the webcam into the shared store."""
    if not _CV2_AVAILABLE:
        log.error("frame_capture_disabled", reason="cv2 not installed")
        return

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    if not cap.isOpened():
        log.error("webcam_open_failed", device="/dev/video0")
        return

    log.info("webcam_opened", width=FRAME_WIDTH, height=FRAME_HEIGHT)
    loop = asyncio.get_event_loop()

    try:
        while True:
            ret, frame = await loop.run_in_executor(None, cap.read)
            if ret:
                encode_params = [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY]
                ok, buf = cv2.imencode(".jpg", frame, encode_params)
                if ok:
                    store.put(bytes(buf))
            await asyncio.sleep(CAPTURE_INTERVAL_S)
    finally:
        cap.release()
        log.info("webcam_closed")


async def _http_server(store: _FrameStore) -> None:
    """Serve the latest frame over plain HTTP on port 8888."""

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            # Read request line (ignore headers for simplicity).
            await reader.readline()
            while True:
                line = await reader.readline()
                if line in (b"\r\n", b"\n", b""):
                    break

            jpeg = store.get()
            if jpeg is None:
                status = b"HTTP/1.1 503 No Frame Yet\r\n"
                writer.write(status + b"Content-Length: 0\r\n\r\n")
            else:
                headers = (
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Cache-Control: no-store\r\n"
                    b"Access-Control-Allow-Origin: *\r\n"
                    + f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
                )
                writer.write(headers + jpeg)
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    server = await asyncio.start_server(handle_client, "0.0.0.0", FRAME_SERVER_PORT)
    log.info("frame_http_server_started", port=FRAME_SERVER_PORT)
    async with server:
        await server.serve_forever()


async def _foundry_publisher(store: _FrameStore, client, cfg) -> None:
    """Publish FrameThumbnail events to Foundry raw_telemetry periodically."""
    from ..comms.protocol import encode_telemetry

    while True:
        await asyncio.sleep(FOUNDRY_EMIT_INTERVAL_S)
        jpeg = store.get()
        if jpeg is None:
            continue
        try:
            b64 = base64.b64encode(jpeg).decode("ascii")
            envelope = encode_telemetry(
                sender=f"drone-{cfg.drone_id}",
                event="FrameThumbnail",
                fields={
                    "format": "jpeg",
                    "width": FRAME_WIDTH,
                    "height": FRAME_HEIGHT,
                    "b64": b64,
                },
            )
            await client.post_telemetry([envelope])
            log.debug("frame_published_to_foundry", bytes=len(jpeg))
        except Exception as exc:
            log.warning("frame_publish_failed", error=str(exc))


async def run_frame_server(client, cfg) -> None:
    """Start all frame server tasks. Call as asyncio.create_task(run_frame_server(...))."""
    store = _FrameStore()
    await asyncio.gather(
        _capture_loop(store, cfg),
        _http_server(store),
        _foundry_publisher(store, client, cfg),
    )
