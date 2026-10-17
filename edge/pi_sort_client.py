"""Pi-side sort client for TossIQ.

Stands in for the eventual Raspberry Pi deployment. Unlike webcam.py (which
uploads the raw frame over the network to get a fast decision from /sort),
this client runs the fast YOLOE model locally and triggers the physical
sort mechanism with zero network dependency -- sorting keeps working even
when the network/cloud is unreachable.

The captured JPEG + fast result are then handed off to a local durable
queue (queue_store.py) for upload to the server's advanced-analysis
`/enrich` endpoint. A background thread drains that queue; it never blocks
capture/sort and silently retries on any failure.

Press SPACE to capture, Q to quit -- same UX as webcam.py, since both stand
in for the same not-yet-built hardware today.

Run (in a separate terminal from the API):
    python edge/pi_sort_client.py
    python edge/pi_sort_client.py --camera 1
    python edge/pi_sort_client.py --url http://127.0.0.1:8000/enrich
    python edge/pi_sort_client.py --location "Vanderbilt Dining Hall"
"""

import argparse
import logging
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import actuator
from fast_sort import detect as fast_detect
from fast_sort import load_fast_model

from edge.queue_store import DEFAULT_BASE_PATH, enqueue, list_pending, mark_sent

logger = logging.getLogger("tossiq")

DEFAULT_SERVER_URL = "http://127.0.0.1:8000/enrich"
UPLOAD_INTERVAL_SECONDS = 5
REQUEST_TIMEOUT_SECONDS = 30
JPEG_CONTENT_TYPE = "image/jpeg"

CATEGORY_COLORS = {
    "recycling": (255, 191, 0),   # blue (BGR)
    "compost": (0, 165, 255),     # orange
    "landfill": (0, 0, 220),      # red
    "unknown": (160, 160, 160),   # gray
}


def process_capture(frame, model, location, base_path) -> dict | None:
    """Runs the fast sort decision, triggers the actuator, and queues the
    frame for upload -- all without any network dependency."""
    result = fast_detect(model, frame)
    actuator.trigger_sort_mechanism(result["category"])

    ok, jpeg = cv2.imencode(".jpg", frame)
    if not ok:
        logger.error("Could not encode frame as JPEG; sort completed but item will not be queued for upload")
        return result

    metadata = {
        "label": result["label"],
        "category": result["category"],
        "confidence": result["confidence"],
        "location": location,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    enqueue(jpeg.tobytes(), metadata, base_path=base_path)

    return result


def _upload_item(item: dict, url: str, base_path) -> None:
    metadata = item["metadata"]
    files = {"file": (f"{item['item_id']}.jpg", item["image_path"].read_bytes(), JPEG_CONTENT_TYPE)}
    data = {}
    if metadata.get("category") is not None:
        data["fast_category"] = metadata["category"]
    if metadata.get("label") is not None:
        data["fast_label"] = metadata["label"]
    if metadata.get("confidence") is not None:
        data["fast_confidence"] = metadata["confidence"]
    if metadata.get("location"):
        data["location"] = metadata["location"]
    if metadata.get("timestamp"):
        data["captured_at"] = metadata["timestamp"]

    try:
        response = requests.post(url, files=files, data=data, timeout=REQUEST_TIMEOUT_SECONDS)
    except requests.exceptions.RequestException:
        logger.info("Could not reach server for queued item %s; will retry", item["item_id"])
        return

    if response.status_code == 200:
        mark_sent(item["item_id"], base_path=base_path)
    else:
        logger.info(
            "Server rejected queued item %s (status %s); will retry",
            item["item_id"],
            response.status_code,
        )


def upload_loop(base_path, url: str, stop_event: threading.Event) -> None:
    """Background loop: periodically drains the local queue to the server.

    Never raises -- a failed attempt just leaves the item queued for the
    next cycle, whether the server is unreachable or rejects it outright.
    """
    while not stop_event.is_set():
        for item in list_pending(base_path=base_path):
            try:
                _upload_item(item, url, base_path)
            except Exception:
                logger.exception("Unexpected error uploading item %s; will retry", item["item_id"])
        stop_event.wait(UPLOAD_INTERVAL_SECONDS)


def draw_overlay(frame, status: str, color) -> None:
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - 40), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, dst=frame)

    cv2.putText(frame, status, (12, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    hint = "SPACE: sort   Q: quit"
    cv2.putText(frame, hint, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)


def main():
    parser = argparse.ArgumentParser(description="TossIQ Pi-side fast-sort client (hardware stand-in)")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index (default 0; use 1+ for an external USB webcam)")
    parser.add_argument("--url", default=DEFAULT_SERVER_URL, help=f"TossIQ /enrich URL for the upload loop (default {DEFAULT_SERVER_URL})")
    parser.add_argument("--location", default=None, help="Bin location to attach to queued events, e.g. 'Vanderbilt Dining Hall'")
    parser.add_argument("--queue-dir", default=str(DEFAULT_BASE_PATH), help=f"Local durable queue directory (default {DEFAULT_BASE_PATH})")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open camera index {args.camera}. "
            "On macOS, check System Settings > Privacy & Security > Camera and grant access to your terminal/IDE, "
            "then re-run. If you have an external webcam, try --camera 1."
        )

    logger.info("Loading fast sort model...")
    model = load_fast_model()

    stop_event = threading.Event()
    upload_thread = threading.Thread(
        target=upload_loop, args=(args.queue_dir, args.url, stop_event), daemon=True
    )
    upload_thread.start()

    window = "TossIQ Pi Client"
    status = "Press SPACE to sort"
    color = CATEGORY_COLORS["unknown"]

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Warning: failed to read frame from camera, retrying...")
                time.sleep(0.05)
                continue

            draw_overlay(frame, status, color)
            cv2.imshow(window, frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord(" "):
                result = process_capture(frame.copy(), model, args.location, args.queue_dir)
                if result is not None:
                    status = f"{result['category'].upper()}  ({result['label'] or 'unrecognized'})"
                    color = CATEGORY_COLORS.get(result["category"], CATEGORY_COLORS["unknown"])
    finally:
        stop_event.set()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
