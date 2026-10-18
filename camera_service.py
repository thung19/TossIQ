"""Background camera + YOLO service for the Linear-styled Live Sorting page.

Runs continuously once FastAPI starts (see api.py lifespan). Each tick:
  1. Reads the newest frame from the configured webcam.
  2. Runs the lightweight YOLOE detector (same model as fast_sort.py).
  3. Stores the raw JPEG + the detection list for the MJPEG stream route
     and the WebSocket subscribers.
  4. Debounces per-label auto-persist of high-confidence detections into
     WASTE_EVENTS so the dashboard filmstrip + KPIs populate without the
     operator having to press anything.

Camera overlays (bounding boxes) are intentionally NOT drawn into the JPEG
-- the frontend draws them in SVG so they inherit the Linear palette and
stay crisp at any zoom. The MJPEG stream is the raw frame; detections ride
alongside on the WebSocket channel.
"""

import asyncio
import logging
import os
import threading
import time
from typing import Any

import cv2

logger = logging.getLogger("tossiq")

WEBCAM_INDEX = int(os.environ.get("TOSSIQ_WEBCAM_INDEX", "0"))
JPEG_QUALITY = int(os.environ.get("TOSSIQ_JPEG_QUALITY", "70"))
CONFIDENCE_THRESHOLD = 0.25
AUTO_PERSIST_CONFIDENCE = 0.55
AUTO_PERSIST_DEBOUNCE_SECONDS = 4.0
SUBSCRIBER_QUEUE_SIZE = 16

BINS: dict[str, str] = {
    "bottle": "recycling",
    "can": "recycling",
    "cardboard box": "recycling",
    "newspaper": "recycling",
    "paper": "recycling",
    "plastic container": "recycling",
    "banana": "compost",
    "apple": "compost",
    "cup": "landfill",
    "plastic bag": "landfill",
    "food container": "landfill",
    "food wrapper": "landfill",
    "expo marker": "landfill",
    "eraser": "landfill",
}

CLASSES: list[str] = list(BINS.keys()) + ["human face"]


class CameraService:
    def __init__(self) -> None:
        self._frame_lock = threading.Lock()
        self._latest_jpeg: bytes | None = None
        self._latest_detections: list[dict] = []
        self._subscribers: set[asyncio.Queue] = set()
        self._subscribers_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._last_persisted_at: dict[str, float] = {}
        self._stats: dict[str, Any] = {
            "running": False,
            "camera_opened": False,
            "frames": 0,
            "detections": 0,
            "last_inference_ms": None,
            "started_at": None,
            "error": None,
        }

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._thread is not None:
            return
        self._loop = loop
        self._thread = threading.Thread(target=self._run, daemon=True, name="tossiq-camera")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    def _run(self) -> None:
        try:
            from ultralytics import YOLOE
        except Exception as exc:
            self._stats["error"] = f"ultralytics import failed: {exc}"
            logger.exception("Camera service: ultralytics import failed")
            return

        try:
            model = YOLOE("yoloe-11s-seg.pt")
            model.set_classes(CLASSES, model.get_text_pe(CLASSES))
        except Exception as exc:
            self._stats["error"] = f"model load failed: {exc}"
            logger.exception("Camera service: model load failed")
            return

        cap = cv2.VideoCapture(WEBCAM_INDEX)
        if not cap.isOpened():
            self._stats["error"] = f"webcam index {WEBCAM_INDEX} could not be opened"
            logger.warning(self._stats["error"])
            return

        self._stats["camera_opened"] = True
        self._stats["running"] = True
        self._stats["started_at"] = time.time()
        logger.info("Camera service running on webcam index %s", WEBCAM_INDEX)

        try:
            while not self._stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.1)
                    continue

                t0 = time.perf_counter()
                try:
                    results = model.predict(frame, conf=CONFIDENCE_THRESHOLD, verbose=False)
                except Exception:
                    logger.exception("Camera service: inference failed")
                    time.sleep(0.1)
                    continue
                inference_ms = int((time.perf_counter() - t0) * 1000)

                boxes = results[0].boxes
                names = results[0].names
                detections: list[dict] = []
                if boxes is not None and len(boxes) > 0:
                    xyxyn = boxes.xyxyn.tolist()
                    confs = boxes.conf.tolist()
                    clss = boxes.cls.tolist()
                    for (x1, y1, x2, y2), conf, cls in zip(xyxyn, confs, clss):
                        label = names[int(cls)]
                        detections.append(
                            {
                                "x1": float(x1),
                                "y1": float(y1),
                                "x2": float(x2),
                                "y2": float(y2),
                                "label": label,
                                "confidence": float(conf),
                                "category": BINS.get(label),
                            }
                        )

                ok_enc, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
                if ok_enc:
                    jpeg_bytes = buf.tobytes()
                    with self._frame_lock:
                        self._latest_jpeg = jpeg_bytes
                        self._latest_detections = detections
                        self._stats["frames"] += 1
                        self._stats["detections"] += len(detections)
                        self._stats["last_inference_ms"] = inference_ms

                event = {
                    "timestamp": time.time(),
                    "inference_ms": inference_ms,
                    "detections": detections,
                }
                self._broadcast(event)

                for d in detections:
                    self._maybe_persist(d)

        finally:
            cap.release()
            self._stats["running"] = False
            logger.info("Camera service stopped")

    def _broadcast(self, event: dict) -> None:
        if self._loop is None:
            return
        with self._subscribers_lock:
            subs = list(self._subscribers)
        for q in subs:
            self._loop.call_soon_threadsafe(self._offer, q, event)

    @staticmethod
    def _offer(q: asyncio.Queue, event: dict) -> None:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
                q.put_nowait(event)
            except Exception:
                pass

    def _maybe_persist(self, d: dict) -> None:
        if d["confidence"] < AUTO_PERSIST_CONFIDENCE or not d["category"]:
            return
        now = time.time()
        last = self._last_persisted_at.get(d["label"], 0.0)
        if now - last < AUTO_PERSIST_DEBOUNCE_SECONDS:
            return
        self._last_persisted_at[d["label"]] = now
        self._persist_async(d)

    def _persist_async(self, d: dict) -> None:
        threading.Thread(target=self._persist, args=(d,), daemon=True).start()

    def _persist(self, d: dict) -> None:
        """Logs one detection. This rig reports LOCATION 'live-webcam', which is
        a rig name and not a can code, so the can it feeds is named by
        LIVE_CAMERA_CAN_CODE and resolved here; unset means the capture is
        logged with no can attributed to it."""
        try:
            import db

            can_code = os.environ.get("LIVE_CAMERA_CAN_CODE", "").strip()
            db.insert_waste_event(
                detected_object=d["label"],
                category=d["category"],
                # WASTE_EVENTS.CONFIDENCE is a percentage: api.py's advanced
                # path writes 0-100 into the same column, and the dashboard
                # and the analytics accuracy view read it as one. The detector
                # reports a 0-1 score, so it is scaled here rather than
                # leaving two different units in one column -- which is what
                # it was doing, making every aggregate over it meaningless.
                confidence=round(d["confidence"] * 100, 2),
                location="live-webcam",
                bin_id=db.can_id_for_code(can_code) if can_code else None,
            )
        except Exception:
            logger.exception("Camera service: auto-persist failed")

    def latest_jpeg(self) -> bytes | None:
        with self._frame_lock:
            return self._latest_jpeg

    def latest_detections(self) -> list[dict]:
        with self._frame_lock:
            return list(self._latest_detections)

    def stats(self) -> dict:
        with self._frame_lock:
            return dict(self._stats)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        with self._subscribers_lock:
            self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        with self._subscribers_lock:
            self._subscribers.discard(q)


camera_service = CameraService()
