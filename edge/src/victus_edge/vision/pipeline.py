"""Vision capture and detection.

Three pieces:

- `WebcamSource`: an async generator yielding JPEG-encoded frames from a
  USB camera via OpenCV. Works on every platform but the YUY2->BGR convert
  + libjpeg encode burns a few ms of CPU per frame.

- `GstSource`: same interface, but the capture pipeline runs through
  GStreamer with Tegra-native plugins (`nvvidconv` for color conversion,
  `nvjpegenc` for JPEG encode on the VIC). Jetson-only — soft-imports
  `gi.repository.Gst` so the package stays importable elsewhere.

- `VisionPipeline` / `Detection`: Phase 2 detector pipeline scaffolding.
  Reads from a source, runs a YOLOv8n-class model, emits Detection events.
  Still stubs.
"""

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator

import structlog


log = structlog.get_logger(__name__)


@dataclass
class Detection:
    detection_id: str
    cls: str
    confidence: float
    bbox: tuple[int, int, int, int]   # x, y, w, h in pixels
    frame_ref: str | None             # populated if a thumbnail was emitted


class WebcamSource:
    """Yields JPEG-encoded frames from a USB webcam at a fixed cadence.

    The OpenCV VideoCapture API is blocking, so reads run in a worker thread
    via asyncio.to_thread to keep the event loop responsive.
    """

    def __init__(
        self,
        device_index: int,
        fps: float = 1.0,
        jpeg_quality: int = 80,
    ) -> None:
        self._device_index = device_index
        self._fps = max(fps, 0.1)  # guard against div-by-zero / runaway loops
        self._jpeg_quality = jpeg_quality

    async def frames(self) -> AsyncIterator[bytes]:
        try:
            import cv2  # noqa: PLC0415 — soft import for optional dep
        except ImportError as e:
            raise RuntimeError(
                "opencv not installed; install with `pip install opencv-python-headless` "
                "or `pip install -e .[vision]`"
            ) from e

        cap = await asyncio.to_thread(cv2.VideoCapture, self._device_index)
        if not cap.isOpened():
            raise RuntimeError(
                f"could not open webcam at /dev/video{self._device_index} — "
                "check `--device /dev/video0` is passed to docker run, "
                "or pick a different --webcam index"
            )
        log.info("webcam_opened", device_index=self._device_index, fps=self._fps)

        period = 1.0 / self._fps
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(self._jpeg_quality)]

        try:
            while True:
                ok, frame = await asyncio.to_thread(cap.read)
                if not ok or frame is None:
                    log.warning("webcam_read_failed_retrying")
                    await asyncio.sleep(period)
                    continue

                ok, buf = cv2.imencode(".jpg", frame, encode_params)
                if not ok:
                    log.warning("webcam_jpeg_encode_failed")
                    await asyncio.sleep(period)
                    continue

                yield bytes(buf)
                await asyncio.sleep(period)
        finally:
            await asyncio.to_thread(cap.release)
            log.info("webcam_closed", device_index=self._device_index)


class GstSource:
    """Yields JPEG-encoded frames from a USB webcam via the Tegra hardware path.

    Pipeline: `v4l2src ! video/x-raw,format=YUY2 ! nvvidconv !
    video/x-raw(memory:NVMM),format=I420 ! nvjpegenc ! appsink`. nvvidconv
    + nvjpegenc run on the Jetson's VIC so the CPU stays free for the
    Python harness and llama-server.

    `appsink.pull_sample` is blocking, so we wrap it in `asyncio.to_thread`
    — same async-bridge pattern WebcamSource uses for cv2.read. No
    GLib.MainLoop needed; appsink fills its internal buffer queue
    automatically once the pipeline is PLAYING.

    `max-buffers=1 drop=true` on the appsink gives "latest frame only"
    semantics: the camera produces at native rate (5 fps on the test cam),
    we pull at our consumer rate, intermediate frames are dropped.
    """

    def __init__(
        self,
        device_index: int,
        fps: float = 1.0,
        jpeg_quality: int = 80,
        width: int = 640,
        height: int = 480,
    ) -> None:
        self._device_index = device_index
        self._fps = max(fps, 0.1)
        self._jpeg_quality = jpeg_quality
        # `width` / `height` are the OUTPUT size after nvvidconv. Default 640x480
        # matches cv2.VideoCapture's typical default and keeps the resulting JPEG
        # under llama-server's 2048-token context budget — at 1920x1080 the mmproj
        # produces ~2059 tokens, overflowing the slot.
        self._width = width
        self._height = height

    def _build_pipeline_string(self) -> str:
        # Let v4l2src negotiate the camera's preferred input resolution; do the
        # downscale on nvvidconv via output caps so the resize runs on the VIC
        # alongside the colorspace conversion and NVMM upload (one hardware pass).
        out_caps = (
            f"video/x-raw(memory:NVMM),format=I420,"
            f"width={self._width},height={self._height}"
        )
        return (
            f"v4l2src device=/dev/video{self._device_index} io-mode=2 "
            f"! video/x-raw,format=YUY2 "
            f"! nvvidconv "
            f"! {out_caps} "
            f"! nvjpegenc quality={self._jpeg_quality} "
            f"! appsink name=sink max-buffers=1 drop=true sync=false"
        )

    async def frames(self) -> AsyncIterator[bytes]:
        try:
            import gi  # noqa: PLC0415 — soft import for Jetson-only dep
            gi.require_version("Gst", "1.0")
            from gi.repository import Gst  # noqa: PLC0415
        except (ImportError, ValueError) as e:
            raise RuntimeError(
                "PyGObject / GStreamer not available — "
                "this path is Jetson-only. Use --webcam N for the cv2 fallback."
            ) from e

        Gst.init(None)
        pipeline_str = self._build_pipeline_string()
        log.info("gst_pipeline_starting", pipeline=pipeline_str)
        pipeline = Gst.parse_launch(pipeline_str)
        appsink = pipeline.get_by_name("sink")

        ret = pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            bus = pipeline.get_bus()
            msg = bus.timed_pop_filtered(Gst.SECOND, Gst.MessageType.ERROR)
            err = msg.parse_error() if msg else "unknown error"
            pipeline.set_state(Gst.State.NULL)
            raise RuntimeError(
                f"gstreamer pipeline failed to start: {err} — "
                "verify nvjpegenc is registered (`gst-inspect-1.0 nvjpegenc` "
                "inside the container) and `--device /dev/video0` is on docker run"
            )
        log.info("gst_pipeline_playing", device_index=self._device_index, fps=self._fps)

        period = 1.0 / self._fps
        try:
            while True:
                sample = await asyncio.to_thread(appsink.emit, "pull-sample")
                if sample is None:
                    log.warning("gst_eos_or_no_sample")
                    break
                buf = sample.get_buffer()
                ok, mapinfo = buf.map(Gst.MapFlags.READ)
                if not ok:
                    log.warning("gst_buffer_map_failed")
                    await asyncio.sleep(period)
                    continue
                try:
                    jpeg = bytes(mapinfo.data)
                finally:
                    buf.unmap(mapinfo)
                yield jpeg
                await asyncio.sleep(period)
        finally:
            pipeline.set_state(Gst.State.NULL)
            log.info("gst_pipeline_stopped", device_index=self._device_index)


class VisionPipeline:
    def __init__(self, source: str) -> None:
        self.source = source

    async def run(self, out_queue) -> None:
        """Loop: capture → detect → enqueue. To be implemented in Phase 2."""
        raise NotImplementedError
