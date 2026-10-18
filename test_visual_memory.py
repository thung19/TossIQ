"""Unit tests for the visual-memory features: unknown-item clustering,
similar-item lookup, embedding persistence, and the guarantee that a failed
embedding never costs the disposal event.

Mocks db.get_connection (plain stdlib unittest.mock, same style as
test_hazard_status.py) so nothing here needs OCI credentials. The grouping
tests drive db._group_by_similarity with fabricated embedding vectors and
assert on the groups it returns -- observable grouping behaviour, not the
source of the algorithm. They use short vectors rather than real 1536-dim
Cohere embeddings because the grouping is dimension-agnostic; only the
VECTOR(1536) column binding cares about width.
"""

import io
import unittest
from unittest import mock

from PIL import Image

import api
import backfill_event_embeddings
import db
import image_embed
import oci_storage


# Three mutually orthogonal directions (cosine distance 1.0 between any two)
# plus a near-duplicate of each, so "same item" and "different item" are
# unambiguous at any sensible threshold.
X = [1.0, 0.0, 0.0, 0.0]
X_NEAR = [0.99, 0.1, 0.0, 0.0]
X_NEAR_2 = [0.98, 0.0, 0.09, 0.0]
Y = [0.0, 1.0, 0.0, 0.0]
Y_NEAR = [0.08, 0.99, 0.0, 0.0]
Z = [0.0, 0.0, 0.0, 1.0]

THRESHOLD = 0.1


def _event(event_id: int, embedding: list[float], **overrides) -> dict:
    event = {
        "event_id": event_id,
        "detected_object": f"object {event_id}",
        "material": "plastic",
        "category": "landfill",
        "location": "kitchen",
        "image_key": f"events/{event_id}.jpg",
        "created_at": None,
        "embedding": embedding,
    }
    event.update(overrides)
    return event


class CosineDistanceTests(unittest.TestCase):
    def test_identical_vectors_are_zero_distance(self):
        self.assertAlmostEqual(db._cosine_distance(X, list(X)), 0.0, places=9)

    def test_orthogonal_vectors_are_unit_distance(self):
        self.assertAlmostEqual(db._cosine_distance(X, Y), 1.0, places=9)

    def test_magnitude_is_ignored_only_direction_counts(self):
        self.assertAlmostEqual(db._cosine_distance(X, [7.0, 0.0, 0.0, 0.0]), 0.0, places=9)

    def test_zero_vector_is_maximally_distant_rather_than_dividing_by_zero(self):
        self.assertEqual(db._cosine_distance(X, [0.0, 0.0, 0.0, 0.0]), 1.0)


class GroupBySimilarityTests(unittest.TestCase):
    def test_items_within_the_threshold_group_together(self):
        groups = db._group_by_similarity(
            [_event(1, X), _event(2, X_NEAR), _event(3, X_NEAR_2)], THRESHOLD
        )

        self.assertEqual(len(groups), 1)
        self.assertEqual([m["event_id"] for m in groups[0]], [1, 2, 3])

    def test_items_outside_the_threshold_do_not_group(self):
        groups = db._group_by_similarity([_event(1, X), _event(2, Y), _event(3, Z)], THRESHOLD)

        self.assertEqual([[m["event_id"] for m in g] for g in groups], [[1], [2], [3]])

    def test_every_event_lands_in_exactly_one_group(self):
        events = [
            _event(1, X),
            _event(2, Y),
            _event(3, X_NEAR),
            _event(4, Z),
            _event(5, Y_NEAR),
            _event(6, X_NEAR_2),
        ]

        groups = db._group_by_similarity(events, THRESHOLD)

        grouped_ids = [m["event_id"] for group in groups for m in group]
        self.assertEqual(sorted(grouped_ids), [1, 2, 3, 4, 5, 6])
        self.assertEqual(len(grouped_ids), len(set(grouped_ids)))

    def test_groups_are_ordered_by_size_descending(self):
        # Input order deliberately puts the one-member group first and the
        # largest group in the middle, so size ordering is what is asserted.
        events = [
            _event(1, Z),
            _event(2, X),
            _event(3, X_NEAR),
            _event(4, X_NEAR_2),
            _event(5, Y),
            _event(6, Y_NEAR),
        ]

        groups = db._group_by_similarity(events, THRESHOLD)

        self.assertEqual([len(g) for g in groups], [3, 2, 1])
        self.assertEqual([m["event_id"] for m in groups[0]], [2, 3, 4])

    def test_the_seed_is_each_group_first_member(self):
        groups = db._group_by_similarity([_event(9, X), _event(1, X_NEAR)], THRESHOLD)

        self.assertEqual(groups[0][0]["event_id"], 9)

    def test_no_events_yields_no_groups(self):
        self.assertEqual(db._group_by_similarity([], THRESHOLD), [])

    def test_a_wider_threshold_merges_what_a_narrow_one_separates(self):
        events = [_event(1, X), _event(2, Y)]

        self.assertEqual(len(db._group_by_similarity(events, 0.1)), 2)
        self.assertEqual(len(db._group_by_similarity(events, 1.0)), 1)


def _mock_connection(rows):
    """A db.get_connection stand-in whose cursor returns `rows`."""
    cursor = mock.MagicMock()
    cursor.fetchall.return_value = rows
    conn = mock.MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    get_connection = mock.MagicMock()
    get_connection.return_value.__enter__.return_value = conn
    return get_connection, cursor


# Row shape of cluster_unknown_events' query: event_id, detected_object,
# material, category, location, image_key, created_at, image_embedding.
def _row(event_id, embedding, created_at=None):
    return (event_id, f"object {event_id}", "plastic", "landfill", "kitchen",
            f"events/{event_id}.jpg", created_at, embedding)


class ClusterUnknownEventsTests(unittest.TestCase):
    def test_repeated_unknown_item_is_reported_as_one_cluster(self):
        get_connection, _ = _mock_connection([_row(1, X), _row(2, X_NEAR), _row(3, Y)])
        with mock.patch("db.get_connection", get_connection):
            result = db.cluster_unknown_events(days=7, max_distance=THRESHOLD)

        self.assertEqual(result["window_days"], 7)
        self.assertEqual(result["unmatched_events"], 3)
        self.assertEqual(len(result["clusters"]), 1)
        cluster = result["clusters"][0]
        self.assertEqual(cluster["size"], 2)
        self.assertEqual(cluster["representative_event_id"], 1)
        self.assertEqual([m["event_id"] for m in cluster["members"]], [1, 2])

    def test_single_sightings_are_not_reported_as_clusters(self):
        get_connection, _ = _mock_connection([_row(1, X), _row(2, Y), _row(3, Z)])
        with mock.patch("db.get_connection", get_connection):
            result = db.cluster_unknown_events(max_distance=THRESHOLD)

        self.assertEqual(result["clusters"], [])
        self.assertEqual(result["unmatched_events"], 3)

    def test_clusters_are_ordered_most_repeated_first(self):
        rows = [_row(1, Y), _row(2, Y_NEAR), _row(3, X), _row(4, X_NEAR), _row(5, X_NEAR_2)]
        get_connection, _ = _mock_connection(rows)
        with mock.patch("db.get_connection", get_connection):
            result = db.cluster_unknown_events(max_distance=THRESHOLD)

        self.assertEqual([c["size"] for c in result["clusters"]], [3, 2])

    def test_members_carry_their_image_key_and_no_raw_embedding(self):
        get_connection, _ = _mock_connection([_row(1, X), _row(2, X_NEAR)])
        with mock.patch("db.get_connection", get_connection):
            result = db.cluster_unknown_events(max_distance=THRESHOLD)

        member = result["clusters"][0]["members"][0]
        self.assertEqual(member["image_key"], "events/1.jpg")
        self.assertNotIn("embedding", member)

    def test_member_timestamps_are_formatted_and_bound_the_window(self):
        import datetime

        rows = [
            _row(1, X, datetime.datetime(2026, 10, 15, 9, 30, 0)),
            _row(2, X_NEAR, datetime.datetime(2026, 10, 12, 8, 0, 0)),
        ]
        get_connection, _ = _mock_connection(rows)
        with mock.patch("db.get_connection", get_connection):
            cluster = db.cluster_unknown_events(max_distance=THRESHOLD)["clusters"][0]

        self.assertEqual(cluster["first_seen"], "2026-10-12 08:00:00")
        self.assertEqual(cluster["last_seen"], "2026-10-15 09:30:00")
        self.assertEqual(cluster["members"][0]["created_at"], "2026-10-15 09:30:00")

    def test_no_unmatched_events_yields_an_empty_report_not_an_error(self):
        get_connection, _ = _mock_connection([])
        with mock.patch("db.get_connection", get_connection):
            result = db.cluster_unknown_events()

        self.assertEqual(result["unmatched_events"], 0)
        self.assertEqual(result["clusters"], [])
        self.assertEqual(result["max_distance"], db.UNKNOWN_CLUSTER_MAX_DISTANCE)


class FindSimilarEventsTests(unittest.TestCase):
    def test_unknown_event_id_raises_lookup_error(self):
        get_connection, cursor = _mock_connection([])
        cursor.fetchone.return_value = None
        with mock.patch("db.get_connection", get_connection):
            with self.assertRaises(LookupError):
                db.find_similar_events(404)

    def test_neighbours_are_returned_with_their_distance(self):
        get_connection, cursor = _mock_connection([])
        cursor.fetchone.return_value = (1,)
        cursor.description = [
            ("EVENT_ID",), ("DETECTED_OBJECT",), ("MATERIAL",), ("CATEGORY",),
            ("LOCATION",), ("IMAGE_KEY",), ("CREATED_AT",), ("DISTANCE",),
        ]
        cursor.fetchall.return_value = [
            (2, "fork", "plastic", "landfill", "kitchen", "events/2.jpg", None, 0.04),
        ]
        with mock.patch("db.get_connection", get_connection):
            similar = db.find_similar_events(1, limit=3)

        self.assertEqual(len(similar), 1)
        self.assertEqual(similar[0]["event_id"], 2)
        self.assertAlmostEqual(similar[0]["distance"], 0.04)


class InsertWasteEventEmbeddingTests(unittest.TestCase):
    """The stored-embedding half of the feature: an embedding is bound through
    TO_VECTOR, and its absence stores NULL rather than failing the insert."""

    def _insert(self, **kwargs):
        get_connection, cursor = _mock_connection([])
        cursor.var.return_value.getvalue.return_value = [7]
        with mock.patch("db.get_connection", get_connection):
            event_id = db.insert_waste_event(**kwargs)
        sql, binds = cursor.execute.call_args[0][0], cursor.execute.call_args[1]
        return event_id, sql, binds

    def test_an_embedding_is_bound_through_to_vector(self):
        event_id, sql, binds = self._insert(detected_object="fork", image_embedding=[0.5, 0.25])

        self.assertEqual(event_id, 7)
        self.assertIn("TO_VECTOR(:image_embedding_str, 1536, FLOAT32)", sql)
        self.assertEqual(binds["image_embedding_str"], "[0.5,0.25]")

    def test_a_missing_embedding_stores_null_and_still_returns_an_event_id(self):
        event_id, sql, binds = self._insert(detected_object="fork", image_embedding=None)

        self.assertEqual(event_id, 7)
        self.assertNotIn("TO_VECTOR", sql)
        self.assertNotIn("image_embedding_str", binds)


class EmbeddingFailureDoesNotCostTheEventTests(unittest.TestCase):
    """api._persist_advanced_result's contract: image_embed.embed_image returns
    None on failure, and the disposal event must still persist."""

    def setUp(self):
        self.image = Image.new("RGB", (4, 4))
        self.identification = {"object": "fork", "material": "plastic"}
        self.sorting = {"category": "landfill"}

    def _persist(self, embedding):
        with (
            mock.patch("api.image_embed.embed_image", return_value=embedding) as embed,
            mock.patch("api._upload_event_image", return_value="events/abc.jpg"),
            mock.patch("api.db.has_any_reference_embedding", return_value=False),
            mock.patch("api.db.match_product", return_value=None),
            mock.patch("api.db.match_product_by_image") as match_by_image,
            mock.patch("api.db.insert_waste_event", return_value=42) as insert,
        ):
            event_id, matched_product = api._persist_advanced_result(
                self.image, self.identification, self.sorting, "kitchen"
            )
        return event_id, matched_product, embed, insert, match_by_image

    def test_a_failed_embedding_still_persists_the_event_with_no_embedding(self):
        event_id, matched_product, _, insert, _ = self._persist(None)

        self.assertEqual(event_id, 42)
        self.assertIsNone(matched_product)
        self.assertIsNone(insert.call_args[1]["image_embedding"])

    def test_a_failed_embedding_is_not_passed_to_catalog_vector_matching(self):
        _, _, _, _, match_by_image = self._persist(None)

        match_by_image.assert_not_called()

    def test_a_successful_embedding_is_stored_on_the_event(self):
        embedding = [0.1] * 1536
        _, _, embed, insert, _ = self._persist(embedding)

        embed.assert_called_once()
        self.assertEqual(insert.call_args[1]["image_embedding"], embedding)

    def test_the_embedding_is_computed_even_with_no_catalog_reference_image(self):
        # The embedding used to be computed only when the catalog could use it.
        # It is stored now, so it is computed regardless.
        _, _, embed, insert, _ = self._persist([0.2] * 1536)

        embed.assert_called_once()
        self.assertIsNotNone(insert.call_args[1]["image_embedding"])


class BackfillTests(unittest.TestCase):
    """The backfill's reporting and skip behaviour. Its re-runnability comes
    from the work queue itself -- db.list_events_missing_embedding only returns
    events with no stored embedding -- so what is asserted here is that it
    skips rather than fails on an unreadable image or a failed embedding call,
    and that the tally it reports matches what it did."""

    PENDING = [
        {"event_id": 1, "image_key": "events/1.jpg"},
        {"event_id": 2, "image_key": "events/2.jpg"},
    ]

    @staticmethod
    def _jpeg_bytes():
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4)).save(buffer, format="JPEG")
        return buffer.getvalue()

    def test_every_readable_image_is_embedded_and_stored(self):
        with (
            mock.patch.object(db, "list_events_missing_embedding", return_value=self.PENDING),
            mock.patch.object(oci_storage, "download_image", return_value=self._jpeg_bytes()),
            mock.patch.object(image_embed, "embed_image", return_value=[0.1] * 4),
            mock.patch.object(db, "set_event_embedding") as store,
        ):
            tally = backfill_event_embeddings.backfill()

        self.assertEqual(tally, {"pending": 2, "embedded": 2, "missing_image": 0, "embed_failed": 0})
        self.assertEqual([call[0][0] for call in store.call_args_list], [1, 2])

    def test_a_missing_image_is_skipped_and_reported_not_raised(self):
        with (
            mock.patch.object(db, "list_events_missing_embedding", return_value=self.PENDING),
            mock.patch.object(oci_storage, "download_image", return_value=None),
            mock.patch.object(image_embed, "embed_image") as embed,
            mock.patch.object(db, "set_event_embedding") as store,
        ):
            tally = backfill_event_embeddings.backfill()

        self.assertEqual(tally["missing_image"], 2)
        self.assertEqual(tally["embedded"], 0)
        embed.assert_not_called()
        store.assert_not_called()

    def test_an_unreadable_stored_object_is_skipped_not_raised(self):
        with (
            mock.patch.object(db, "list_events_missing_embedding", return_value=self.PENDING[:1]),
            mock.patch.object(oci_storage, "download_image", return_value=b"not an image"),
            mock.patch.object(image_embed, "embed_image") as embed,
            mock.patch.object(db, "set_event_embedding") as store,
        ):
            tally = backfill_event_embeddings.backfill()

        self.assertEqual(tally["missing_image"], 1)
        embed.assert_not_called()
        store.assert_not_called()

    def test_a_failed_embedding_call_leaves_the_event_for_a_later_run(self):
        with (
            mock.patch.object(db, "list_events_missing_embedding", return_value=self.PENDING[:1]),
            mock.patch.object(oci_storage, "download_image", return_value=self._jpeg_bytes()),
            mock.patch.object(image_embed, "embed_image", return_value=None),
            mock.patch.object(db, "set_event_embedding") as store,
        ):
            tally = backfill_event_embeddings.backfill()

        self.assertEqual(tally["embed_failed"], 1)
        store.assert_not_called()

    def test_a_dry_run_writes_nothing(self):
        with (
            mock.patch.object(db, "list_events_missing_embedding", return_value=self.PENDING),
            mock.patch.object(oci_storage, "download_image") as download,
            mock.patch.object(image_embed, "embed_image") as embed,
            mock.patch.object(db, "set_event_embedding") as store,
        ):
            tally = backfill_event_embeddings.backfill(dry_run=True)

        self.assertEqual(tally["pending"], 2)
        self.assertEqual(tally["embedded"], 0)
        download.assert_not_called()
        embed.assert_not_called()
        store.assert_not_called()


if __name__ == "__main__":
    unittest.main()
