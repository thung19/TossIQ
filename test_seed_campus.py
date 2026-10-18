"""Idempotency tests for seed_campus.py.

The seed is run repeatedly against a live shared database, so "a second run
inserts nothing" is the property that matters most about it -- and it is the
property that cannot be checked by reading the script. These tests mock db.py's
write helpers (plain stdlib unittest.mock, no live OCI connection, same style
as test_insights.py) and assert the seed's skip logic directly.
"""

import itertools
import random
import unittest
from unittest import mock

import seed_campus


def fake_cans(count: int = 3, simulated: bool = True) -> dict[str, dict]:
    return {
        f"VU-RAND-{index:02d}": {
            "can_id": index,
            "model_code": "TQ-S-120",
            "profile": "dining",
            "is_simulated": 1 if simulated else 0,
        }
        for index in range(1, count + 1)
    }


class InventoryUpsertTests(unittest.TestCase):
    """CAN_MODELS / BUILDINGS / CANS are keyed on their natural codes, so
    idempotency is delegated to db._upsert's insert-or-skip."""

    @mock.patch("seed_campus.db.upsert_can_model", return_value=7)
    def test_models_are_keyed_on_model_code(self, mock_upsert):
        models = seed_campus.seed_models()
        self.assertEqual(set(models), {spec["model_code"] for spec in seed_campus.CAN_MODELS})
        passed_codes = [call.args[0] for call in mock_upsert.call_args_list]
        self.assertEqual(passed_codes, [spec["model_code"] for spec in seed_campus.CAN_MODELS])
        # model_code must never be duplicated in the keyword payload too --
        # that would make the INSERT name the same column twice.
        for call in mock_upsert.call_args_list:
            self.assertNotIn("model_code", call.kwargs)

    @mock.patch("seed_campus.db.upsert_building", return_value=3)
    def test_buildings_are_keyed_on_building_code(self, mock_upsert):
        buildings = seed_campus.seed_buildings()
        self.assertEqual(len(buildings), len(seed_campus.BUILDINGS))
        self.assertEqual(
            [call.args[0] for call in mock_upsert.call_args_list],
            [row[0] for row in seed_campus.BUILDINGS],
        )

    @mock.patch("seed_campus.db.upsert_can", side_effect=itertools.count(1))
    def test_cans_are_keyed_on_can_code_and_cover_every_layout_slot(self, mock_upsert):
        models = {spec["model_code"]: {"model_id": 1, **spec} for spec in seed_campus.CAN_MODELS}
        buildings = {row[0]: 1 for row in seed_campus.BUILDINGS}

        cans = seed_campus.seed_cans(models, buildings)

        expected = sum(len(model_codes) for _code, model_codes in seed_campus.CAN_LAYOUT)
        self.assertEqual(len(cans), expected)
        self.assertEqual(len(set(cans)), expected, "can_code must be unique across the fleet")
        for can_code in cans:
            self.assertRegex(can_code, r"^VU-[A-Z']+-\d{2}$")

    def test_can_positions_are_reproducible_for_a_fixed_seed(self):
        first = seed_campus.can_position(random.Random(1), 36.145, -86.803)
        second = seed_campus.can_position(random.Random(1), 36.145, -86.803)
        self.assertEqual(first, second)

    def test_can_positions_stay_within_a_short_walk_of_the_building(self):
        rng = random.Random(seed_campus.RANDOM_SEED)
        for _ in range(200):
            latitude, longitude = seed_campus.can_position(rng, 36.145, -86.803)
            self.assertLess(abs(latitude - 36.145), 0.0005)
            self.assertLess(abs(longitude + 86.803), 0.0005)


class AppendOnlyTableSkipTests(unittest.TestCase):
    """CAN_READINGS / SERVICE_EVENTS / WASTE_EVENTS have no natural key to
    collide on, so the seed skips any can that already has rows."""

    @mock.patch("seed_campus.db.count_rows_by_can")
    @mock.patch("seed_campus._insert_batch")
    def test_readings_are_seeded_for_a_can_with_none(self, mock_insert, mock_counts):
        mock_counts.return_value = {}
        mock_insert.side_effect = lambda sql, rows: len(rows)

        inserted = seed_campus.seed_readings(fake_cans(3))

        expected_per_can = seed_campus.READING_TAIL_DAYS * seed_campus.READINGS_PER_DAY
        self.assertEqual(inserted, 3 * expected_per_can)

    @mock.patch("seed_campus.db.count_rows_by_can")
    @mock.patch("seed_campus._insert_batch")
    def test_readings_are_not_seeded_twice(self, mock_insert, mock_counts):
        mock_counts.return_value = {1: 28, 2: 28, 3: 28}
        mock_insert.side_effect = lambda sql, rows: len(rows)

        self.assertEqual(seed_campus.seed_readings(fake_cans(3)), 0)
        self.assertEqual(mock_insert.call_args.args[1], [])

    @mock.patch("seed_campus.db.count_rows_by_can")
    @mock.patch("seed_campus._insert_batch")
    def test_only_the_cans_missing_a_tail_are_topped_up(self, mock_insert, mock_counts):
        mock_counts.return_value = {1: 28}
        mock_insert.side_effect = lambda sql, rows: len(rows)

        inserted = seed_campus.seed_readings(fake_cans(3))

        expected_per_can = seed_campus.READING_TAIL_DAYS * seed_campus.READINGS_PER_DAY
        self.assertEqual(inserted, 2 * expected_per_can)
        seeded_can_ids = {row["can_id"] for row in mock_insert.call_args.args[1]}
        self.assertEqual(seeded_can_ids, {2, 3})

    @mock.patch("seed_campus.db.count_rows_by_can")
    @mock.patch("seed_campus._insert_batch")
    def test_service_history_is_not_seeded_twice(self, mock_insert, mock_counts):
        mock_counts.return_value = {1: 3, 2: 3, 3: 3}
        mock_insert.side_effect = lambda sql, rows: len(rows)

        self.assertEqual(seed_campus.seed_service_events(fake_cans(3)), 0)

    @mock.patch("seed_campus.db.count_rows_by_can")
    @mock.patch("seed_campus._insert_batch")
    def test_every_can_gets_an_emptying_history(self, mock_insert, mock_counts):
        mock_counts.return_value = {}
        mock_insert.side_effect = lambda sql, rows: len(rows)

        seed_campus.seed_service_events(fake_cans(3))

        rows = mock_insert.call_args.args[1]
        self.assertEqual(sum(1 for row in rows if row["service_type"] == "emptied"), 9)

    @mock.patch("seed_campus.db.match_product", return_value=None)
    @mock.patch("seed_campus.db.count_waste_events_by_can")
    @mock.patch("seed_campus._insert_batch")
    def test_synthetic_events_are_not_seeded_twice(self, mock_insert, mock_counts, _match):
        mock_counts.return_value = {1: 12, 2: 12, 3: 12}
        mock_insert.side_effect = lambda sql, rows: len(rows)

        self.assertEqual(seed_campus.seed_waste_events(fake_cans(3)), 0)

    @mock.patch("seed_campus.db.match_product", return_value=None)
    @mock.patch("seed_campus.db.count_waste_events_by_can")
    @mock.patch("seed_campus._insert_batch")
    def test_real_cans_never_receive_synthetic_events(self, mock_insert, mock_counts, _match):
        mock_counts.return_value = {}
        mock_insert.side_effect = lambda sql, rows: len(rows)

        self.assertEqual(seed_campus.seed_waste_events(fake_cans(3, simulated=False)), 0)

    @mock.patch("seed_campus.db.match_product", return_value=None)
    @mock.patch("seed_campus.db.count_waste_events_by_can")
    @mock.patch("seed_campus._insert_batch")
    def test_synthetic_events_are_tagged_with_their_can_code_as_location(self, mock_insert, mock_counts, _match):
        mock_counts.return_value = {}
        mock_insert.side_effect = lambda sql, rows: len(rows)

        seed_campus.seed_waste_events(fake_cans(2))

        rows = mock_insert.call_args.args[1]
        self.assertTrue(rows)
        for row in rows:
            self.assertRegex(row["location"], r"^VU-RAND-\d{2}$")
            self.assertEqual(row["location"], f"VU-RAND-{row['bin_id']:02d}")
            self.assertIn(row["category"], ("recycling", "compost", "landfill"))

    @mock.patch("seed_campus.db.match_product")
    @mock.patch("seed_campus.db.count_waste_events_by_can")
    @mock.patch("seed_campus._insert_batch")
    def test_catalog_match_is_resolved_once_per_distinct_object(self, mock_insert, mock_counts, mock_match):
        mock_counts.return_value = {}
        mock_insert.side_effect = lambda sql, rows: len(rows)
        mock_match.return_value = {"product_id": 21}

        seed_campus.seed_waste_events(fake_cans(3))

        queried = [call.args[0] for call in mock_match.call_args_list]
        self.assertEqual(len(queried), len(set(queried)), "matcher must be cached per object name")
        for row in mock_insert.call_args.args[1]:
            self.assertEqual(row["product_id"], 21)


class BackfillTests(unittest.TestCase):
    def test_legacy_locations_map_only_to_can_codes_the_seed_creates(self):
        seeded_codes = {
            f"{building_code}-{index:02d}"
            for building_code, model_codes in seed_campus.CAN_LAYOUT
            for index in range(1, len(model_codes) + 1)
        }
        for location, can_code in seed_campus.LEGACY_LOCATION_TO_CAN_CODE.items():
            self.assertIn(can_code, seeded_codes, f"{location!r} maps to an unseeded can")

    def test_the_real_cans_are_the_backfill_targets(self):
        self.assertEqual(
            set(seed_campus.LEGACY_LOCATION_TO_CAN_CODE.values()),
            seed_campus.REAL_CAN_CODES,
        )


if __name__ == "__main__":
    unittest.main()
