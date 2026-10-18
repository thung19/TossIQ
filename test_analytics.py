"""Unit tests for analytics.py's shaping, and for the dimension whitelist.

Pure functions over fabricated rows with db patched out -- no live OCI
connection, same style as test_fleet.py -- so the parts most likely to be
misread later (what a cost total includes, what "accuracy" counts, what
happens when nothing is in scope) are pinned without credentials.
"""

import unittest
from unittest import mock

import analytics
import db


def raw(**overrides) -> dict:
    """One raw grouped row as db.analytics_distribution returns it."""
    row = {
        "bucket": "plastic",
        "n": 10,
        "matched_n": 8,
        "matched_cost": 12.50,
        "matched_grams": 400.0,
        "class_cost": 2.00,
        "class_grams": 80.0,
        "no_cost_n": 1,
        "hazard_n": 2,
        "hazard_critical_n": 1,
        "avg_confidence": 81.25,
    }
    row.update(overrides)
    return row


class MeasureTests(unittest.TestCase):
    def test_cost_and_mass_combine_matched_and_class_average_portions(self):
        measures = analytics._measures(raw())
        self.assertEqual(measures["estimated_cost"], 14.50)
        self.assertEqual(measures["estimated_grams"], 480.0)
        self.assertEqual(measures["estimated_kg"], 0.48)

    def test_cost_provenance_is_reported_separately_from_the_total(self):
        """A total built mostly from class averages is worth showing, but not
        worth acting on without knowing that is what it is."""
        measures = analytics._measures(raw())
        self.assertEqual(measures["cost_from_matched"], 12.50)
        self.assertEqual(measures["cost_from_class_average"], 2.00)
        self.assertEqual(
            round(measures["cost_from_matched"] + measures["cost_from_class_average"], 2),
            measures["estimated_cost"],
        )

    def test_items_with_no_catalog_entry_are_counted_not_treated_as_free(self):
        measures = analytics._measures(raw(no_cost_n=4))
        self.assertEqual(measures["no_cost_items"], 4)

    def test_zero_confidence_reports_none_rather_than_zero(self):
        # avg_confidence 0 means "nothing scored", not "scored zero".
        self.assertIsNone(analytics._measures(raw(avg_confidence=0.0))["avg_confidence"])


class DistributionTests(unittest.TestCase):
    def shaped(self, rows, total_n=None):
        total = {"n": total_n if total_n is not None else sum(r["n"] for r in rows),
                 "matched_n": 0, "matched_cost": 0.0, "matched_grams": 0.0,
                 "class_cost": 0.0, "class_grams": 0.0, "no_cost_n": 0,
                 "hazard_n": 0, "hazard_critical_n": 0, "avg_confidence": 0.0}
        with mock.patch.object(analytics.db, "analytics_distribution", return_value=rows), \
             mock.patch.object(analytics.db, "analytics_totals", return_value=total):
            return analytics.distribution("material", days=30)

    def test_shares_are_computed_against_the_rows_returned(self):
        result = self.shaped([raw(bucket="a", n=30), raw(bucket="b", n=10)])
        self.assertEqual([row["share"] for row in result["rows"]], [75.0, 25.0])

    def test_a_limited_query_is_flagged_as_truncated(self):
        """A pie chart whose slices sum to less than the total has to say so,
        or the missing tail reads as a bug."""
        result = self.shaped([raw(n=30)], total_n=100)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["shown_count"], 30)
        self.assertEqual(result["total_count"], 100)

    def test_a_complete_query_is_not_flagged(self):
        result = self.shaped([raw(n=30), raw(bucket="b", n=70)], total_n=100)
        self.assertFalse(result["truncated"])

    def test_empty_scope_yields_zero_shares_rather_than_dividing_by_zero(self):
        result = self.shaped([], total_n=0)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["total_count"], 0)


class OverviewTests(unittest.TestCase):
    def overview(self, categories, totals=None):
        total = totals or {"n": sum(r["n"] for r in categories), "matched_n": 0,
                           "matched_cost": 0.0, "matched_grams": 0.0, "class_cost": 0.0,
                           "class_grams": 0.0, "no_cost_n": 0, "avg_confidence": 0.0}
        with mock.patch.object(analytics.db, "analytics_totals", return_value=total), \
             mock.patch.object(analytics.db, "analytics_distribution", return_value=categories):
            return analytics.overview(days=30)

    def test_diversion_counts_recycling_and_compost_only(self):
        result = self.overview([
            raw(bucket="recycling", n=50),
            raw(bucket="compost", n=20),
            raw(bucket="landfill", n=30),
        ])
        self.assertEqual(result["diverted_items"], 70)
        self.assertEqual(result["diversion_rate"], 70.0)

    def test_an_unknown_category_does_not_count_as_diverted(self):
        """An item the system could not classify has not been diverted; it has
        not been anything. Counting it either way would be a claim."""
        result = self.overview([raw(bucket="recycling", n=50), raw(bucket="unknown", n=50)])
        self.assertEqual(result["diversion_rate"], 50.0)

    def test_empty_window_reports_zero_rather_than_failing(self):
        result = self.overview([], totals={"n": 0, "matched_n": 0, "matched_cost": 0.0,
                                           "matched_grams": 0.0, "class_cost": 0.0,
                                           "class_grams": 0.0, "no_cost_n": 0,
                                           "hazard_n": 0, "hazard_critical_n": 0,
                                           "avg_confidence": 0.0})
        self.assertEqual(result["diversion_rate"], 0.0)
        self.assertEqual(result["catalog_match_rate"], 0.0)

    def test_estimate_notes_are_served_with_the_numbers_they_qualify(self):
        """The mass caveat has to travel with the figure. A reader who sees
        37 kg without it will assume something weighed it."""
        result = self.overview([raw(bucket="landfill", n=10)])
        self.assertIn("weight sensor", result["estimate_notes"]["mass"])
        self.assertIn("0.00", result["estimate_notes"]["cost"])


class AccuracyTests(unittest.TestCase):
    def review(self, verdict="correct", confidence=85.0, category="recycling",
               detected_object="aluminum can", corrected_object=None):
        return {
            "event_id": 1, "detected_object": detected_object, "category": category,
            "confidence": confidence, "verdict": verdict,
            "corrected_category": None, "corrected_object": corrected_object,
        }

    def accuracy(self, reviews, total_events=100):
        totals = {"n": total_events, "matched_n": 0, "matched_cost": 0.0,
                  "matched_grams": 0.0, "class_cost": 0.0, "class_grams": 0.0,
                  "no_cost_n": 0, "hazard_n": 0, "hazard_critical_n": 0,
                  "avg_confidence": 0.0}
        with mock.patch.object(analytics.db, "analytics_review_rows", return_value=reviews), \
             mock.patch.object(analytics.db, "analytics_totals", return_value=totals):
            return analytics.accuracy(days=30)

    def test_accuracy_is_agreement_over_the_reviewed_sample(self):
        result = self.accuracy([self.review()] * 9 + [self.review(verdict="incorrect")])
        self.assertEqual(result["accuracy"], 90.0)
        self.assertEqual(result["reviewed_events"], 10)

    def test_coverage_is_reported_so_a_rate_cannot_pass_for_the_whole_fleet(self):
        result = self.accuracy([self.review()] * 10, total_events=1000)
        self.assertEqual(result["review_coverage"], 1.0)
        self.assertEqual(result["total_events"], 1000)

    def test_nothing_reviewed_reports_none_not_zero_accuracy(self):
        """Zero would read as "the classifier got everything wrong", which is
        the opposite of "nobody has checked"."""
        result = self.accuracy([])
        self.assertIsNone(result["accuracy"])
        self.assertEqual(result["reviewed_events"], 0)

    def test_confidence_buckets_use_the_highest_bound_the_value_clears(self):
        result = self.accuracy([
            self.review(confidence=55.0), self.review(confidence=65.0),
            self.review(confidence=75.0), self.review(confidence=85.0),
            self.review(confidence=95.0),
        ])
        self.assertEqual([b["reviewed"] for b in result["calibration"]], [1, 1, 1, 1, 1])

    def test_a_boundary_value_lands_in_the_bucket_it_names(self):
        result = self.accuracy([self.review(confidence=90.0)])
        by_label = {b["label"]: b["reviewed"] for b in result["calibration"]}
        self.assertEqual(by_label["90%+"], 1)
        self.assertEqual(by_label["80-89%"], 0)

    def test_unscored_reviews_are_excluded_from_calibration_and_counted(self):
        result = self.accuracy([self.review(confidence=None), self.review(confidence=85.0)])
        self.assertEqual(result["unscored_reviews"], 1)
        self.assertEqual(sum(b["reviewed"] for b in result["calibration"]), 1)
        # They still count towards the headline rate -- a review is a review.
        self.assertEqual(result["reviewed_events"], 2)

    def test_confusions_pair_what_was_seen_with_what_it_was(self):
        result = self.accuracy([
            self.review(verdict="incorrect", detected_object="cup",
                        corrected_object="styrofoam cup"),
            self.review(verdict="incorrect", detected_object="cup",
                        corrected_object="styrofoam cup"),
            self.review(),
        ])
        self.assertEqual(result["confusions"][0],
                         {"seen_as": "cup", "actually_was": "styrofoam cup", "count": 2})

    def test_correct_verdicts_never_appear_as_confusions(self):
        result = self.accuracy([self.review()] * 5)
        self.assertEqual(result["confusions"], [])


class MisroutedTests(unittest.TestCase):
    def test_rate_is_against_all_items_in_scope_not_just_misrouted_ones(self):
        rows = [{"item": "x", "logged_as": "landfill", "should_be": "compost",
                 "count": 20, "grams": 500.0}]
        totals = {"n": 200, "matched_n": 0, "matched_cost": 0.0, "matched_grams": 0.0,
                  "class_cost": 0.0, "class_grams": 0.0, "no_cost_n": 0,
                  "hazard_n": 0, "hazard_critical_n": 0, "avg_confidence": 0.0}
        with mock.patch.object(analytics.db, "analytics_misrouted", return_value=rows), \
             mock.patch.object(analytics.db, "analytics_totals", return_value=totals):
            result = analytics.misrouted(days=30)
        self.assertEqual(result["misrouted_rate"], 10.0)
        self.assertEqual(result["rows"][0]["estimated_kg"], 0.5)


class CatalogRollupTests(unittest.TestCase):
    PRODUCT = {
        "product_id": 1, "sku": "DISP-CUP-H12", "product_name": "Paper Hot Cup 12 oz",
        "brand": "Imperial Dade", "variant_label": "12 oz", "supplier": "Imperial Dade",
        "material": "paper", "material_subtype": "poly-lined paperboard",
        "unit_cost": 0.11, "unit_weight_grams": 11.0, "disposal_category": "landfill",
        "recyclable": 0, "reusable": 0, "case_pack_qty": 1000, "case_cost": 94.0,
        "active": 1, "detected_as": "cup",
    }

    def rollup(self, rows):
        with mock.patch.object(analytics.db, "list_products", return_value=[self.PRODUCT]), \
             mock.patch.object(analytics.db, "analytics_distribution", return_value=rows):
            return analytics.catalog_rollup(days=30)

    def test_case_equivalent_converts_counts_into_the_purchasing_unit(self):
        """Nobody orders cups singly, so "1,500 cups" is not actionable and
        "1.5 cases" is."""
        result = self.rollup([raw(bucket="DISP-CUP-H12", n=1500)])
        self.assertEqual(result["skus"][0]["cases_equivalent"], 1.5)

    def test_a_sku_with_no_case_pack_reports_no_case_equivalent(self):
        product = {**self.PRODUCT, "case_pack_qty": None}
        with mock.patch.object(analytics.db, "list_products", return_value=[product]), \
             mock.patch.object(analytics.db, "analytics_distribution", return_value=[raw(bucket="DISP-CUP-H12", n=10)]):
            result = analytics.catalog_rollup(days=30)
        self.assertIsNone(result["skus"][0]["cases_equivalent"])

    def test_an_unmatched_bucket_survives_with_null_catalog_fields(self):
        """The unmatched row is the honest part of this table and must not be
        dropped for having no product behind it."""
        result = self.rollup([raw(bucket="unmatched", n=28)])
        row = result["skus"][0]
        self.assertEqual(row["sku"], "unmatched")
        self.assertIsNone(row["product_name"])
        self.assertEqual(row["count"], 28)


class DimensionWhitelistTests(unittest.TestCase):
    """The dimension arrives from a query string, so it must select a key
    rather than reach the SQL as text."""

    def test_an_unknown_dimension_raises_before_any_query_runs(self):
        with mock.patch.object(db, "get_connection") as connect:
            with self.assertRaises(ValueError):
                db.analytics_distribution("1; DROP TABLE waste_events--")
        connect.assert_not_called()

    def test_the_error_names_the_valid_dimensions(self):
        with self.assertRaises(ValueError) as caught:
            db.analytics_distribution("nonsense")
        self.assertIn("material", str(caught.exception))

    def test_time_dimensions_sort_chronologically_not_by_volume(self):
        """A date series ordered by count is a leaderboard with dates for
        labels; no trend can be read off it."""
        self.assertEqual(db.ORDERED_DIMENSIONS, {"hour", "weekday", "day"})
        for name in db.ORDERED_DIMENSIONS:
            self.assertIn(name, db.ANALYTICS_DIMENSIONS)

    def test_every_dimension_expression_is_null_safe(self):
        """A NULL bucket becomes a JSON null the UI renders as a blank row, so
        each expression has to name its own unknown case."""
        for name, expression in db.ANALYTICS_DIMENSIONS.items():
            if name in db.ORDERED_DIMENSIONS:
                continue  # TO_CHAR over a NOT NULL timestamp
            self.assertIn("COALESCE", expression, name)


class FilterBindingTests(unittest.TestCase):
    """Filter values are binds, never interpolated, and every analytics query
    accepts the same set -- a filter that silently does nothing on one tab is
    worse than one that errors."""

    def test_every_filter_becomes_a_bind_not_sql_text(self):
        where, binds = db._analytics_filters(
            30, 4, None, "recycling", "plastic", "aluminum can", "US Foods"
        )
        self.assertNotIn("recycling", where)
        self.assertIn(":category", where)
        self.assertEqual(binds["category"], "recycling")
        self.assertEqual(binds["supplier"], "US Foods")

    def test_no_filters_produces_no_where_clause(self):
        where, binds = db._analytics_filters(None, None, None, None, None, None, None)
        self.assertEqual(where, "")
        self.assertEqual(binds, {})

    def test_the_grouped_and_ungrouped_queries_take_the_same_filters(self):
        import inspect

        shared = {"days", "building_id", "can_id", "category", "material",
                  "detected_object", "supplier"}
        for function in (
            db.analytics_distribution,
            db.analytics_totals,
            db.analytics_misrouted,
            db.analytics_bin_composition,
            db.analytics_review_rows,
        ):
            parameters = set(inspect.signature(function).parameters)
            self.assertTrue(
                shared <= parameters,
                f"{function.__name__} is missing {sorted(shared - parameters)}",
            )


class HazardInAnalyticsTests(unittest.TestCase):
    """Hazards travel with every breakdown rather than living only on their
    own page. "Which building throws away the most" and "which throws away
    the most dangerous things" are different questions and should not need
    different tabs."""

    def test_hazard_counts_ride_along_on_every_measure_block(self):
        measures = analytics._measures(raw(hazard_n=5, hazard_critical_n=2))
        self.assertEqual(measures["hazard_items"], 5)
        self.assertEqual(measures["hazard_critical_items"], 2)

    def test_an_older_row_without_the_columns_reports_zero_not_an_error(self):
        """analytics._measures is fed by several queries; one that predates
        the hazard columns must degrade rather than raise."""
        row = raw()
        del row["hazard_n"]
        del row["hazard_critical_n"]
        self.assertEqual(analytics._measures(row)["hazard_items"], 0)

    def test_overview_reports_a_hazard_rate_against_everything_logged(self):
        totals = {"n": 1000, "matched_n": 0, "matched_cost": 0.0, "matched_grams": 0.0,
                  "class_cost": 0.0, "class_grams": 0.0, "no_cost_n": 0,
                  "hazard_n": 30, "hazard_critical_n": 12, "avg_confidence": 0.0}
        with mock.patch.object(analytics.db, "analytics_totals", return_value=totals), \
             mock.patch.object(analytics.db, "analytics_distribution", return_value=[]):
            result = analytics.overview(days=30)
        self.assertEqual(result["hazard_rate"], 3.0)
        self.assertIn("critical", result["estimate_notes"]["hazards"])

    def test_the_hazard_dimension_keeps_non_hazards_visible(self):
        """Bucketing them out entirely would make the hazard slice look
        like the only thing on campus."""
        expression = db.ANALYTICS_DIMENSIONS["hazard_class"]
        self.assertIn("not hazardous", expression)
        self.assertIn("hazard_flag = 1", expression)

    def test_both_hazard_dimensions_are_whitelisted(self):
        for name in ("hazard_class", "hazard_severity"):
            self.assertIn(name, db.ANALYTICS_DIMENSIONS)


if __name__ == "__main__":
    unittest.main()
