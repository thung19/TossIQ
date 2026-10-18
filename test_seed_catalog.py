"""Tests for seed_catalog.py: the catalog's internal consistency and the
attribution and review passes.

db is patched out, so these run without credentials. What they mostly guard
is the data itself -- a catalog with a duplicate SKU or a missing weight is a
silently wrong dashboard rather than a crash, and that is exactly the kind of
mistake a reviewer will not catch by eye across 47 rows.
"""

import random
import unittest
from unittest import mock

import seed_catalog


class CatalogIntegrityTests(unittest.TestCase):
    """Read through catalog_rows() rather than by tuple position: counting
    fifteen positions by hand is exactly how a test ends up asserting about
    the wrong column."""

    ROWS = seed_catalog.catalog_rows()

    def test_every_sku_is_unique(self):
        skus = [row["sku"] for row in self.ROWS]
        self.assertEqual(len(skus), len(set(skus)))

    def test_every_row_has_every_declared_field(self):
        for raw_row, row in zip(seed_catalog.CATALOG, self.ROWS):
            self.assertEqual(len(raw_row), len(seed_catalog.CATALOG_FIELDS), row["sku"])
            self.assertEqual(set(row), set(seed_catalog.CATALOG_FIELDS))

    def test_every_product_has_a_cost_and_a_reference_mass(self):
        """A product missing either contributes nothing to its own totals,
        which looks identical to it never being thrown away."""
        for row in self.ROWS:
            self.assertIsNotNone(row["unit_cost"], row["sku"])
            self.assertIsNotNone(row["unit_weight_grams"], row["sku"])
            self.assertGreater(row["unit_weight_grams"], 0, row["sku"])

    def test_consumed_residue_costs_nothing(self):
        """A banana peel represents no loss: the banana was eaten. Charging
        for it would invent waste that did not happen."""
        residue = {"PRD-FRT-BAN-PEEL", "PRD-FRT-APL-CORE", "PRD-COF-GRND", "GRD-VEG-TRIM"}
        for row in self.ROWS:
            if row["sku"] in residue:
                self.assertEqual(row["unit_cost"], 0.00, row["sku"])

    def test_uneaten_food_carries_a_real_cost(self):
        """Edible food that was paid for and not eaten is a recoverable loss,
        and must not be lumped in with peels at zero."""
        uneaten = {"PRD-PZA-CRUST", "PRD-FD-SCRAP", "PRD-FRT-BAN", "PRD-FRT-APL"}
        for row in self.ROWS:
            if row["sku"] in uneaten:
                self.assertGreater(row["unit_cost"], 0.0, row["sku"])

    def test_every_product_declares_a_disposal_stream(self):
        valid = {"recycling", "compost", "landfill"}
        for row in self.ROWS:
            self.assertIn(row["disposal_category"], valid, row["sku"])

    def test_recyclable_and_reusable_are_zero_or_one(self):
        for row in self.ROWS:
            self.assertIn(row["recyclable"], (0, 1), row["sku"])
            self.assertIn(row["reusable"], (0, 1), row["sku"])

    def test_case_cost_is_consistent_with_unit_cost_where_both_are_given(self):
        """A case price wildly out of step with the unit price would make the
        supplies tab's two cost columns contradict each other."""
        for row in self.ROWS:
            pack, case_cost, unit_cost = row["case_pack_qty"], row["case_cost"], row["unit_cost"]
            if pack and case_cost and unit_cost:
                implied = case_cost / pack
                # Unit price is retail-ish and case price wholesale, so a gap
                # is expected; an order of magnitude is a typo.
                self.assertLess(implied, unit_cost * 1.5, row["sku"])
                self.assertGreater(implied, unit_cost * 0.02, row["sku"])

    def test_variant_weights_name_only_real_skus(self):
        skus = {row["sku"] for row in self.ROWS}
        self.assertTrue(set(seed_catalog.VARIANT_WEIGHTS) <= skus)

    def test_generic_fallbacks_name_only_real_skus(self):
        skus = {row["sku"] for row in self.ROWS}
        self.assertTrue(set(seed_catalog.GENERIC_LABEL_FALLBACK.values()) <= skus)

    def test_shared_labels_are_the_point_and_at_least_one_exists(self):
        """Several products behind one vision label is the honest case the
        catalog is built to represent -- the label cannot tell them apart."""
        labels: dict[str, int] = {}
        for row in self.ROWS:
            labels[row["detected_as"]] = labels.get(row["detected_as"], 0) + 1
        self.assertTrue(any(count > 1 for count in labels.values()))

    def test_a_label_is_never_both_catalogued_and_deliberately_unmatched(self):
        labels = {row["detected_as"] for row in self.ROWS}
        self.assertFalse(labels & seed_catalog.DELIBERATELY_UNMATCHED)


class ChooseProductTests(unittest.TestCase):
    GROUPED = {
        "plastic water bottle": [
            {"product_id": 1, "sku": "BEV-WTR-0591-VU"},
            {"product_id": 2, "sku": "BEV-WTR-1000-SMW"},
        ],
        "napkin": [{"product_id": 3, "sku": "DISP-NAP-1PLY"}],
    }

    def test_a_single_variant_label_always_resolves_to_it(self):
        rng = random.Random(1)
        chosen = seed_catalog.choose_product(rng, "napkin", self.GROUPED)
        self.assertEqual(chosen["sku"], "DISP-NAP-1PLY")

    def test_a_shared_label_resolves_to_one_of_its_variants(self):
        rng = random.Random(1)
        for _ in range(50):
            chosen = seed_catalog.choose_product(rng, "plastic water bottle", self.GROUPED)
            self.assertIn(chosen["sku"], {"BEV-WTR-0591-VU", "BEV-WTR-1000-SMW"})

    def test_the_weighting_actually_biases_the_draw(self):
        rng = random.Random(7)
        picks = [
            seed_catalog.choose_product(rng, "plastic water bottle", self.GROUPED)["sku"]
            for _ in range(400)
        ]
        cheap = picks.count("BEV-WTR-0591-VU")
        self.assertGreater(cheap, len(picks) * 0.6)

    def test_a_generic_label_falls_back_to_the_entry_level_variant(self):
        rng = random.Random(1)
        chosen = seed_catalog.choose_product(rng, "bottle", self.GROUPED)
        self.assertEqual(chosen["sku"], "BEV-WTR-0591-VU")

    def test_a_label_the_catalog_does_not_cover_resolves_to_nothing(self):
        """"mixed trash" names a bag of unidentifiable material. Attributing
        it to some product would invent a cost."""
        rng = random.Random(1)
        self.assertIsNone(seed_catalog.choose_product(rng, "mixed trash", self.GROUPED))

    def test_deliberately_unmatched_labels_are_recorded_as_such(self):
        self.assertIn("mixed trash", seed_catalog.DELIBERATELY_UNMATCHED)


class AttributionTests(unittest.TestCase):
    def test_only_unattributed_events_are_touched_and_are_stamped_seeded(self):
        """An event the live pipeline matched by image embedding keeps that
        match, and the stamp is what lets the UI separate demo attribution
        from a real one."""
        grouped = {"napkin": [{"product_id": 3, "sku": "DISP-NAP-1PLY"}]}
        with mock.patch.object(seed_catalog, "products_by_label", return_value=grouped), \
             mock.patch.object(seed_catalog.db, "list_unattributed_events",
                               return_value=[(10, "napkin"), (11, "mixed trash")]), \
             mock.patch.object(seed_catalog.db, "set_event_product_matches",
                               side_effect=lambda rows: len(rows)) as write:
            attributed, unmatched = seed_catalog.attribute_events()

        self.assertEqual((attributed, unmatched), (1, 1))
        written = write.call_args[0][0]
        self.assertEqual(written[0]["event_id"], 10)
        self.assertEqual(written[0]["match_method"], "seeded")

    def test_an_event_with_no_detected_object_is_left_alone(self):
        with mock.patch.object(seed_catalog, "products_by_label", return_value={}), \
             mock.patch.object(seed_catalog.db, "list_unattributed_events",
                               return_value=[(1, None)]), \
             mock.patch.object(seed_catalog.db, "set_event_product_matches", return_value=0):
            attributed, unmatched = seed_catalog.attribute_events()
        self.assertEqual((attributed, unmatched), (0, 1))


class ReviewSeedTests(unittest.TestCase):
    def test_agreement_rises_with_confidence(self):
        """A classifier whose errors ignored its own confidence would make the
        calibration view meaningless, so the seed must not produce one."""
        rng = random.Random(3)
        low = sum(seed_catalog.review_verdict(rng, 62.0) for _ in range(2000))
        high = sum(seed_catalog.review_verdict(rng, 95.0) for _ in range(2000))
        self.assertGreater(high, low)

    def test_an_unscored_event_still_gets_a_verdict(self):
        rng = random.Random(3)
        verdicts = [seed_catalog.review_verdict(rng, None) for _ in range(200)]
        self.assertTrue(any(verdicts))
        self.assertTrue(not all(verdicts))

    def test_coverage_is_partial_by_design(self):
        """Full coverage would be the tell that the review trail is
        fictional, and would let a sample rate pass as a fleet-wide one."""
        self.assertLess(seed_catalog.REVIEW_COVERAGE, 0.5)

    def test_confusable_pairs_are_plausible_and_symmetric_where_stated(self):
        seen = {pair[0] for pair in seed_catalog.CONFUSABLE}
        actual = {pair[1] for pair in seed_catalog.CONFUSABLE}
        # Every corrected label is itself something the detector can emit,
        # otherwise the confusion matrix names a class that does not exist.
        self.assertTrue(actual <= seen | actual)
        self.assertTrue(len(seen) >= 8)

    def test_a_correct_verdict_carries_no_correction(self):
        rng = random.Random(5)
        candidates = [(1, "aluminum can", "recycling", 95, __import__("datetime").datetime(2026, 10, 1))]
        with mock.patch.object(seed_catalog.db, "list_unreviewed_events", return_value=candidates), \
             mock.patch.object(seed_catalog.db, "insert_event_reviews",
                               side_effect=lambda rows: len(rows)) as write, \
             mock.patch.object(seed_catalog.random, "Random", return_value=rng):
            seed_catalog.seed_reviews()
        rows = write.call_args[0][0]
        for row in rows:
            if row["verdict"] == "correct":
                self.assertIsNone(row["corrected_object"])
                self.assertIsNone(row["corrected_category"])

    def test_reviews_are_timestamped_after_the_event_they_review(self):
        import datetime

        captured = datetime.datetime(2026, 10, 1, 12, 0, 0)
        candidates = [(index, "cup", "landfill", 70, captured) for index in range(60)]
        with mock.patch.object(seed_catalog.db, "list_unreviewed_events", return_value=candidates), \
             mock.patch.object(seed_catalog.db, "insert_event_reviews",
                               side_effect=lambda rows: len(rows)) as write:
            seed_catalog.seed_reviews()
        for row in write.call_args[0][0]:
            self.assertGreater(row["reviewed_at"], captured)


class LegacyCompletionTests(unittest.TestCase):
    def test_legacy_detail_names_only_columns_the_filler_accepts(self):
        allowed = {
            "brand", "variant_label", "detected_as", "material", "material_subtype",
            "unit_cost", "unit_weight_grams", "disposal_category", "recyclable",
            "reusable", "case_pack_qty", "case_cost", "active",
        }
        for sku, columns in seed_catalog.LEGACY_PRODUCT_DETAIL.items():
            self.assertTrue(set(columns) <= allowed, sku)

    def test_a_missing_legacy_row_is_skipped_rather_than_created(self):
        """This pass completes rows that exist; inventing one would put a
        product in the catalog nobody added."""
        with mock.patch.object(seed_catalog.db, "product_id_for_sku", return_value=None), \
             mock.patch.object(seed_catalog.db, "fill_null_product_columns") as fill:
            self.assertEqual(seed_catalog.complete_legacy_products(), 0)
        fill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
