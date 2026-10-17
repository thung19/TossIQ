"""Unit tests for edge/queue_store.py.

Covers enqueue/list_pending/mark_sent against a real temporary directory --
this module is pure filesystem I/O with no network or DB dependency, so it
is fully testable without hardware or live credentials.
"""

import tempfile
import unittest
from pathlib import Path

from edge import queue_store


class QueueStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.base_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_enqueue_writes_image_and_sidecar(self):
        metadata = {"label": "bottle", "category": "recycling", "confidence": 0.9}
        item_id = queue_store.enqueue(b"fake-jpeg-bytes", metadata, base_path=self.base_path)

        pending = self.base_path / "pending"
        self.assertTrue((pending / f"{item_id}.jpg").exists())
        self.assertTrue((pending / f"{item_id}.json").exists())
        self.assertEqual((pending / f"{item_id}.jpg").read_bytes(), b"fake-jpeg-bytes")

    def test_list_pending_returns_enqueued_items(self):
        metadata = {"label": "can", "category": "recycling", "confidence": 0.8}
        item_id = queue_store.enqueue(b"jpeg-bytes", metadata, base_path=self.base_path)

        items = queue_store.list_pending(base_path=self.base_path)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["item_id"], item_id)
        self.assertEqual(items[0]["metadata"], metadata)

    def test_list_pending_empty_when_nothing_queued(self):
        self.assertEqual(queue_store.list_pending(base_path=self.base_path), [])

    def test_mark_sent_removes_item_from_pending(self):
        metadata = {"label": "bottle", "category": "recycling", "confidence": 0.9}
        item_id = queue_store.enqueue(b"jpeg-bytes", metadata, base_path=self.base_path)

        queue_store.mark_sent(item_id, base_path=self.base_path)

        self.assertEqual(queue_store.list_pending(base_path=self.base_path), [])
        pending = self.base_path / "pending"
        self.assertFalse((pending / f"{item_id}.jpg").exists())
        self.assertFalse((pending / f"{item_id}.json").exists())

    def test_mark_sent_is_safe_for_missing_item(self):
        queue_store.mark_sent("does-not-exist", base_path=self.base_path)  # must not raise

    def test_enqueue_multiple_items_all_listed(self):
        ids = {
            queue_store.enqueue(b"a", {"label": "a"}, base_path=self.base_path),
            queue_store.enqueue(b"b", {"label": "b"}, base_path=self.base_path),
        }
        items = queue_store.list_pending(base_path=self.base_path)
        self.assertEqual({item["item_id"] for item in items}, ids)


if __name__ == "__main__":
    unittest.main()
