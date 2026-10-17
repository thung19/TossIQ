"""Local durable on-disk queue for edge devices with no DB/cloud credentials.

Each pending item is a JPEG file plus a JSON sidecar (fast label/category/
confidence, location, timestamp) written to a `pending/` directory under a
configurable base path. No OCI credentials or database access live here --
only the server side has those; this module is pure filesystem I/O so it can
run standalone on a Raspberry Pi with no network, and `pi_sort_client.py`'s
upload loop drains it whenever the server is reachable.
"""

import json
import time
import uuid
from pathlib import Path

DEFAULT_BASE_PATH = Path("./edge_queue")


def _pending_dir(base_path) -> Path:
    pending = Path(base_path) / "pending"
    pending.mkdir(parents=True, exist_ok=True)
    return pending


def enqueue(image_bytes: bytes, metadata: dict, base_path=DEFAULT_BASE_PATH) -> str:
    """Writes the JPEG + JSON sidecar for one captured item and returns its id."""
    pending = _pending_dir(base_path)
    item_id = f"{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

    (pending / f"{item_id}.jpg").write_bytes(image_bytes)
    (pending / f"{item_id}.json").write_text(json.dumps(metadata))

    return item_id


def list_pending(base_path=DEFAULT_BASE_PATH) -> list[dict]:
    """Returns every queued item still awaiting upload, oldest first."""
    pending = _pending_dir(base_path)
    items = []
    for metadata_path in sorted(pending.glob("*.json")):
        item_id = metadata_path.stem
        image_path = pending / f"{item_id}.jpg"
        if not image_path.exists():
            continue  # partial write, or already-sent item mid-removal
        try:
            metadata = json.loads(metadata_path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        items.append({"item_id": item_id, "image_path": image_path, "metadata": metadata})
    return items


def mark_sent(item_id: str, base_path=DEFAULT_BASE_PATH) -> None:
    """Removes a successfully-uploaded item from the pending queue."""
    pending = _pending_dir(base_path)
    (pending / f"{item_id}.jpg").unlink(missing_ok=True)
    (pending / f"{item_id}.json").unlink(missing_ok=True)
