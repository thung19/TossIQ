"""Live webcam client for TossIQ.

Shows the webcam feed; press SPACE to send the current frame to the
FastAPI `/sort` endpoint and overlay the fast sort decision. That decision
comes back immediately (the lightweight local model); the advanced Qwen
analysis runs afterward in the background on the server and shows up a few
seconds later in the dashboard (http://127.0.0.1:8000/), not here. Press Q
to quit. Inference runs in a background thread so the preview never
freezes, and a capture already in flight blocks new ones until it resolves.

Run (in a separate terminal from the API):
    python webcam.py
    python webcam.py --camera 1          # external USB webcam
    python webcam.py --url http://127.0.0.1:9000/sort
    python webcam.py --location "Vanderbilt Dining Hall"
"""

import argparse
import threading
import time

import cv2
import requests

DEFAULT_API_URL = "http://127.0.0.1:8000/sort"
REQUEST_TIMEOUT_SECONDS = 30

# Matches api.py's ALLOWED_CONTENT_TYPES; jpeg keeps the upload small/fast.
JPEG_CONTENT_TYPE = "image/jpeg"

CATEGORY_COLORS = {
    "recycling": (255, 191, 0),   # blue (BGR)
    "compost": (0, 165, 255),     # orange
    "landfill": (0, 0, 220),      # red
    "unknown": (160, 160, 160),   # gray
}


class ClassifierClient:
    """Owns the one in-flight request at a time; runs it off the UI thread."""

    def __init__(self, url: str, location: str | None = None):
        self.url = url
        self.location = location
        self._lock = threading.Lock()
        self._busy = False
        self.latest_status = "Press SPACE to classify"
        self.latest_lines = []
        self.latest_color = (200, 200, 200)

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy

    def submit(self, frame):
        with self._lock:
            if self._busy:
                return  # a request is already in flight -- drop this press
            self._busy = True
        self.latest_status = "Classifying..."
        thread = threading.Thread(target=self._run, args=(frame,), daemon=True)
        thread.start()

    def _run(self, frame):
        try:
            ok, jpeg = cv2.imencode(".jpg", frame)
            if not ok:
                self._set_error("Could not encode frame as JPEG")
                return

            files = {"file": ("frame.jpg", jpeg.tobytes(), JPEG_CONTENT_TYPE)}
            data = {"location": self.location} if self.location else {}

            start = time.monotonic()
            response = requests.post(self.url, files=files, data=data, timeout=REQUEST_TIMEOUT_SECONDS)
            elapsed_ms = (time.monotonic() - start) * 1000

            if response.status_code != 200:
                detail = self._extract_detail(response)
                self._set_error(f"API error {response.status_code}: {detail}")
                return

            try:
                data = response.json()
            except ValueError:
                self._set_error("API returned invalid JSON")
                return

            self._set_result(data, elapsed_ms)

        except requests.exceptions.Timeout:
            self._set_error(f"Request timed out after {REQUEST_TIMEOUT_SECONDS}s")
        except requests.exceptions.ConnectionError:
            self._set_error("Could not reach API -- is it running?")
        except Exception as e:
            self._set_error(f"Unexpected error: {e}")
        finally:
            with self._lock:
                self._busy = False

    @staticmethod
    def _extract_detail(response) -> str:
        try:
            return str(response.json().get("detail", response.text))
        except ValueError:
            return response.text[:200]

    def _set_error(self, message: str):
        self.latest_status = "ERROR"
        self.latest_lines = [message]
        self.latest_color = CATEGORY_COLORS["unknown"]

    def _set_result(self, data: dict, elapsed_ms: float):
        category = data.get("category") or "unknown"
        label = data.get("label") or "unrecognized"
        confidence = data.get("confidence")
        reason = data.get("reason") or ""
        needs_review = data.get("needs_review")

        self.latest_status = f"{category.upper()}  ({elapsed_ms:.0f} ms)"
        confidence_line = f"Confidence: {confidence:.0%}" if confidence is not None else "Confidence: n/a"
        self.latest_lines = [f"Detected: {label}", confidence_line, f"Reason: {reason}"]
        if needs_review:
            self.latest_lines.append("[flagged for manual review -- not auto-routed]")
        self.latest_lines.append("Advanced analysis running in background -- see dashboard")
        self.latest_color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["unknown"])


def draw_overlay(frame, client: ClassifierClient):
    h, w = frame.shape[:2]
    panel_height = 34 + 24 * (len(client.latest_lines) + 1)
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, h - panel_height), (w, h), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, dst=frame)

    y = h - panel_height + 24
    cv2.putText(frame, client.latest_status, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, client.latest_color, 2)
    for line in client.latest_lines:
        y += 24
        cv2.putText(frame, line[:90], (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    hint = "SPACE: classify   Q: quit"
    cv2.putText(frame, hint, (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    if client.busy:
        cv2.circle(frame, (w - 20, 20), 8, (0, 255, 255), -1)


def main():
    parser = argparse.ArgumentParser(description="TossIQ live webcam classifier client")
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index (default 0; use 1+ for an external USB webcam)")
    parser.add_argument("--url", default=DEFAULT_API_URL, help=f"TossIQ /sort URL (default {DEFAULT_API_URL})")
    parser.add_argument("--location", default=None, help="Bin location to attach to logged events, e.g. 'Vanderbilt Dining Hall'")
    args = parser.parse_args()

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open camera index {args.camera}. "
            "On macOS, check System Settings > Privacy & Security > Camera and grant access to your terminal/IDE, "
            "then re-run. If you have an external webcam, try --camera 1."
        )

    client = ClassifierClient(args.url, location=args.location)
    window = "TossIQ"

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Warning: failed to read frame from camera, retrying...")
                time.sleep(0.05)
                continue

            draw_overlay(frame, client)
            cv2.imshow(window, frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord(" "):
                client.submit(frame.copy())
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
