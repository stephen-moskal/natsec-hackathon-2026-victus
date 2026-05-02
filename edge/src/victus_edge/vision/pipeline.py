"""Vision capture and detection.

Reads frames from the configured source (webcam, video file, or GStreamer
pipeline on Orin), runs a lightweight detector (YOLOv8n-class), and emits
Detection events plus periodic frame samples to the main loop.

Decoupled from the reasoner's tick rate: this module pushes onto a queue;
the reasoner pulls when it is ready to think.
"""

from dataclasses import dataclass


@dataclass
class Detection:
    detection_id: str
    cls: str
    confidence: float
    bbox: tuple[int, int, int, int]   # x, y, w, h in pixels
    frame_ref: str | None             # populated if a thumbnail was emitted


class VisionPipeline:
    def __init__(self, source: str) -> None:
        self.source = source

    async def run(self, out_queue) -> None:
        """Loop: capture → detect → enqueue. To be implemented in Phase 2."""
        raise NotImplementedError
