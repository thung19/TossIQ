"""Unit tests for initiatives.py: measurement, progress and roll-up.

db and analytics are patched out, so no OCI connection. What these guard
is the arithmetic a goal page lives or dies on: progress that reads as
success while a number gets worse, or a baseline that quietly moves, would
make the whole page a liar.
"""

import unittest
from datetime import datetime
from unittest import mock

import initiatives

NOW = datetime(2026, 10, 19, 12, 0, 0)


def goal(**overrides) -> dict:
    row = {
        "initiative_id": 1,
        "name": "Cut bottled water",
        "metric": "items",
        "direction": "reduce",
        "baseline_value": 100.0,
        "baseline_window_days": 30,
        "target_value": 40.0,
        "target_date": "2026-12-01",
        "status": "active",
        "scope_building_id": None,
        "scope_category": None,
        "scope_material": None,
        "scope_object": None,
        "scope_supplier": None,
    }
    row.update(overrides)
    return row


class ScopeTests(unittest.TestCase):
    def test_an_empty_scope_is_campus_wide(self):
        self.assertEqual(initiatives.scope_filters(goal(), 30), {"days": 30})
        self.assertEqual(initiatives.describe_scope(goal()), "campus-wide")

    def test_scope_columns_map_onto_the_analytics_filter_names(self):
        """One mapping, so a goal can only be defined over a slice the
        analytics page can also show."""
        filters = initiatives.scope_filters(
            goal(scope_building_id=4, scope_object="plastic water bottle",
                 scope_category="recycling"),
            14,
        )
        self.assertEqual(filters, {
            "days": 14, "building_id": 4,
            "detected_object": "plastic water bottle", "category": "recycling",
        })

    def test_empty_strings_are_not_filters(self):
        """A blank select in the form must mean "any", not "match the
        empty string", which would return nothing."""
        filters = initiatives.scope_filters(goal(scope_category=""), 30)
        self.assertEqual(filters, {"days": 30})

    def test_a_building_is_described_by_name_not_id(self):
        label = initiatives.describe_scope(goal(scope_building_id=7), {7: "Rand Hall"})
        self.assertEqual(label, "Rand Hall")


class ProgressTests(unittest.TestCase):
    def test_halfway_between_baseline_and_target_is_fifty_percent(self):
        self.assertEqual(initiatives.progress(goal(), 70.0)["percent"], 50.0)

    def test_progress_is_measured_from_the_baseline_not_from_zero(self):
        """current/target would be 175% here -- while the goal is nowhere
        near met. A reduction goal drawn from zero fills up as things get
        worse."""
        result = initiatives.progress(goal(), 70.0)
        self.assertEqual(result["percent"], 50.0)
        self.assertNotEqual(result["percent"], 70.0 / 40.0 * 100)

    def test_reaching_the_target_is_achieved(self):
        self.assertEqual(initiatives.progress(goal(), 40.0)["state"], "achieved")
        self.assertEqual(initiatives.progress(goal(), 20.0)["state"], "achieved")

    def test_going_backwards_reports_a_negative_rather_than_zero(self):
        """"No progress" and "actively losing ground" are different facts,
        and the second is the one worth knowing."""
        result = initiatives.progress(goal(), 130.0)
        self.assertLess(result["percent"], 0)
        self.assertEqual(result["state"], "regressing")

    def test_an_increase_goal_runs_the_other_way(self):
        lift = goal(direction="increase", metric="diversion_rate",
                    baseline_value=57.0, target_value=75.0)
        self.assertEqual(initiatives.progress(lift, 66.0)["percent"], 50.0)
        self.assertEqual(initiatives.progress(lift, 80.0)["state"], "achieved")
        self.assertEqual(initiatives.progress(lift, 50.0)["state"], "regressing")

    def test_states_ladder_with_distance_travelled(self):
        self.assertEqual(initiatives.progress(goal(), 95.0)["state"], "off_track")
        self.assertEqual(initiatives.progress(goal(), 70.0)["state"], "in_progress")
        self.assertEqual(initiatives.progress(goal(), 45.0)["state"], "near_target")

    def test_a_baseline_already_on_target_does_not_divide_by_zero(self):
        flat = goal(baseline_value=40.0, target_value=40.0)
        self.assertEqual(initiatives.progress(flat, 40.0)["state"], "achieved")
        self.assertEqual(initiatives.progress(flat, 50.0)["state"], "off_track")

    def test_an_unmeasurable_goal_says_so_rather_than_reading_zero(self):
        result = initiatives.progress(goal(), None)
        self.assertIsNone(result["percent"])
        self.assertEqual(result["state"], "unmeasured")

    def test_distance_to_target_is_reported_in_the_metric_units(self):
        self.assertEqual(initiatives.progress(goal(), 70.0)["distance_to_target"], -30.0)


class MeasureTests(unittest.TestCase):
    def test_a_metric_measures_over_its_own_scope(self):
        with mock.patch.object(initiatives.db, "analytics_totals",
                               return_value={"n": 42}) as query:
            value = initiatives.measure(goal(scope_object="chip bag"), days=7)
        self.assertEqual(value, 42.0)
        query.assert_called_once_with(days=7, detected_object="chip bag")

    def test_the_window_defaults_to_the_goals_own_baseline_window(self):
        with mock.patch.object(initiatives.db, "analytics_totals",
                               return_value={"n": 1}) as query:
            initiatives.measure(goal(baseline_window_days=90))
        self.assertEqual(query.call_args.kwargs["days"], 90)

    def test_landfill_items_forces_the_category_regardless_of_scope(self):
        """"Items sent to landfill" means landfill even if the goal's scope
        says otherwise, or the metric would measure something else."""
        with mock.patch.object(initiatives.db, "analytics_totals",
                               return_value={"n": 5}) as query:
            initiatives.measure(goal(metric="landfill_items", scope_category="compost"))
        self.assertEqual(query.call_args.kwargs["category"], "landfill")

    def test_an_unknown_metric_is_unmeasurable_rather_than_fatal(self):
        """One goal created against a metric that has since been removed
        must not take the page down with it."""
        self.assertIsNone(initiatives.measure(goal(metric="made_up")))

    def test_accuracy_with_nothing_reviewed_reads_zero_not_none(self):
        with mock.patch.object(initiatives.analytics, "accuracy",
                               return_value={"accuracy": None}):
            self.assertEqual(initiatives.measure(goal(metric="review_accuracy")), 0.0)

    def test_every_metric_declares_what_it_is_and_how_to_read_it(self):
        for key, spec in initiatives.METRICS.items():
            self.assertTrue(spec["label"], key)
            self.assertIn(spec["format"], ("count", "money", "mass", "percent"), key)
            self.assertIsInstance(spec["lower_is_better"], bool)
            self.assertGreater(len(spec["help"]), 20, key)
            self.assertTrue(callable(spec["measure"]), key)


class ResolveTests(unittest.TestCase):
    def project(self, status="in_progress", impact=None) -> dict:
        return {"project_id": 1, "status": status, "expected_impact": impact}

    def resolve(self, projects, current=70.0, **overrides):
        with mock.patch.object(initiatives, "measure", return_value=current):
            return initiatives.resolve(goal(**overrides), projects, {}, now=NOW)

    def test_claimed_impact_counts_only_work_under_way_or_done(self):
        result = self.resolve([
            self.project("in_progress", 100.0),
            self.project("done", 50.0),
            self.project("proposed", 999.0),
            self.project("cancelled", 999.0),
        ])
        self.assertEqual(result["claimed_impact"], 150.0)

    def test_claimed_impact_is_never_folded_into_measured_progress(self):
        """A pile of optimistic estimates must not read as achievement."""
        without = self.resolve([])
        with_claims = self.resolve([self.project("in_progress", 10_000.0)])
        self.assertEqual(without["progress_percent"], with_claims["progress_percent"])

    def test_a_goal_with_no_projects_is_reported_as_such(self):
        self.assertEqual(self.resolve([])["project_count"], 0)

    def test_days_remaining_goes_negative_when_overdue(self):
        result = self.resolve([], target_date="2026-10-01")
        self.assertEqual(result["days_remaining"], -18)

    def test_an_open_ended_goal_has_no_deadline(self):
        self.assertIsNone(self.resolve([], target_date=None)["days_remaining"])


class ListResolvedTests(unittest.TestCase):
    def listing(self, rows, projects=()):
        with mock.patch.object(initiatives.db, "list_initiatives", return_value=list(rows)), \
             mock.patch.object(initiatives.db, "list_projects", return_value=list(projects)), \
             mock.patch.object(initiatives.db, "list_buildings", return_value=[]), \
             mock.patch.object(initiatives, "measure", return_value=70.0):
            return initiatives.list_resolved(now=NOW)

    def test_active_goals_without_projects_are_called_out(self):
        result = self.listing([goal(initiative_id=1), goal(initiative_id=2)])
        self.assertEqual(len(result["unbacked"]), 2)

    def test_a_goal_with_work_is_not_called_unbacked(self):
        result = self.listing(
            [goal(initiative_id=1)],
            [{"project_id": 1, "initiative_id": 1, "status": "proposed",
              "expected_impact": None}],
        )
        self.assertEqual(result["unbacked"], [])

    def test_an_overdue_unmet_goal_is_flagged(self):
        result = self.listing([goal(target_date="2026-09-01")])
        self.assertEqual(len(result["overdue"]), 1)
        self.assertEqual(result["overdue"][0]["days_overdue"], 48)

    def test_an_overdue_but_achieved_goal_is_not_flagged(self):
        """Passing the date having hit the target is not a problem."""
        with mock.patch.object(initiatives.db, "list_initiatives",
                               return_value=[goal(target_date="2026-09-01")]), \
             mock.patch.object(initiatives.db, "list_projects", return_value=[]), \
             mock.patch.object(initiatives.db, "list_buildings", return_value=[]), \
             mock.patch.object(initiatives, "measure", return_value=10.0):
            result = initiatives.list_resolved(now=NOW)
        self.assertEqual(result["overdue"], [])

    def test_metric_specs_are_published_without_their_callables(self):
        """The payload is JSON; a function in it would not serialise."""
        result = self.listing([])
        for spec in result["metrics"].values():
            self.assertNotIn("measure", spec)

    def test_an_empty_workspace_reports_nothing_rather_than_failing(self):
        result = self.listing([])
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["achieved"], 0)


class MaterialityTests(unittest.TestCase):
    """A goal to cut $3 to $1 is a 67% reduction and means nothing. The
    first version of the seeded workspace had exactly that, because the
    slice it measured -- cost of everything in the compost bin -- is almost
    empty once peels are priced at zero."""

    def test_a_trivial_money_goal_is_flagged(self):
        result = initiatives.materiality("cost", 3.0)
        self.assertFalse(result["is_material"])
        self.assertIn("noise", result["note"])

    def test_a_real_money_goal_passes(self):
        self.assertTrue(initiatives.materiality("cost", 7000.0)["is_material"])

    def test_a_rate_has_no_floor(self):
        """3% is 3% whatever the volume behind it."""
        self.assertTrue(initiatives.materiality("contamination_rate", 0.4)["is_material"])
        self.assertTrue(initiatives.materiality("diversion_rate", 2.0)["is_material"])

    def test_safety_is_exempt_whatever_the_count(self):
        """One lithium cell in a compactor is worth a target. Telling
        somebody their hazard goal is too small would be the wrong advice
        from a waste system."""
        self.assertTrue(initiatives.materiality("hazard_events", 3.0)["is_material"])

    def test_a_small_count_goal_is_flagged(self):
        self.assertFalse(initiatives.materiality("items", 12.0)["is_material"])

    def test_an_unmeasurable_baseline_is_not_flagged_as_small(self):
        """Unknown is not the same as tiny, and should not be reported as
        though somebody chose a bad scope."""
        self.assertTrue(initiatives.materiality("cost", None)["is_material"])

    def test_the_note_names_the_floor_it_failed(self):
        self.assertIn("$100", initiatives.materiality("cost", 3.0)["note"])

    def test_resolve_carries_the_verdict_onto_the_card(self):
        with mock.patch.object(initiatives, "measure", return_value=2.0):
            result = initiatives.resolve(
                goal(metric="cost", baseline_value=3.0, target_value=1.0), [], {}, now=NOW
            )
        self.assertFalse(result["is_material"])
        self.assertIsNotNone(result["materiality_note"])


class FoodWasteMetricTests(unittest.TestCase):
    """The food metric counts EDIBLE food only. Scoping a cost goal to the
    compost bin instead measures peels, which are priced at zero because
    the product they came from was eaten."""

    ROWS = [
        {"building": "Rand Hall", "item": "Plate Scrapings", "count": 20,
         "cost": 55.0, "grams": 3800.0},
        {"building": "Commons Center", "item": "Pizza Crust", "count": 10,
         "cost": 3.0, "grams": 450.0},
    ]

    def test_it_sums_catalog_value_of_edible_food(self):
        with mock.patch.object(initiatives.db, "edible_food_waste", return_value=self.ROWS):
            value = initiatives.measure(goal(metric="food_waste_cost"))
        self.assertEqual(value, 58.0)

    def test_a_building_scope_narrows_to_that_building(self):
        with mock.patch.object(initiatives.db, "edible_food_waste", return_value=self.ROWS), \
             mock.patch.object(initiatives.db, "list_buildings",
                               return_value=[{"building_id": 3, "name": "Rand Hall"}]):
            value = initiatives.measure(goal(metric="food_waste_cost", scope_building_id=3))
        self.assertEqual(value, 55.0)

    def test_its_help_text_says_residue_is_excluded(self):
        help_text = initiatives.METRICS["food_waste_cost"]["help"]
        self.assertIn("peels", help_text)


class PaceTests(unittest.TestCase):
    """The half that was missing. "33% of the way" says nothing on its own:
    33% with most of the year left is fine, 33% with a fortnight to go is a
    goal about to be missed."""

    def dated(self, captured: str, target: str, **overrides) -> dict:
        return goal(baseline_captured_at=captured, target_date=target, **overrides)

    def test_progress_matching_time_elapsed_is_on_pace(self):
        # Half the time gone, half the journey done.
        result = initiatives.pace(
            self.dated("2026-08-20 00:00:00", "2026-12-19"), 50.0, now=NOW
        )
        self.assertEqual(result["pace_state"], "on_track")

    def test_running_ahead_of_the_clock_is_ahead(self):
        result = initiatives.pace(
            self.dated("2026-09-19 00:00:00", "2027-01-17"), 60.0, now=NOW
        )
        self.assertEqual(result["pace_state"], "ahead")

    def test_running_behind_the_clock_is_flagged(self):
        result = initiatives.pace(
            self.dated("2026-07-21 00:00:00", "2026-11-19"), 30.0, now=NOW
        )
        self.assertIn(result["pace_state"], ("behind", "at_risk"))

    def test_a_goal_with_no_deadline_is_called_out(self):
        """Permanently on track and never finished -- the "cut it sometime
        over the next decade" problem."""
        result = initiatives.pace(goal(target_date=None), 50.0, now=NOW)
        self.assertEqual(result["pace_state"], "no_deadline")
        self.assertIsNone(result["projected_completion"])

    def test_a_brand_new_goal_is_not_judged(self):
        """Calling a week-old goal "behind" is noise."""
        result = initiatives.pace(
            self.dated("2026-10-18 00:00:00", "2027-10-18"), 0.0, now=NOW
        )
        self.assertEqual(result["pace_state"], "too_early")

    def test_going_backwards_beats_every_other_verdict(self):
        result = initiatives.pace(
            self.dated("2026-08-20 00:00:00", "2026-12-19"), -15.0, now=NOW
        )
        self.assertEqual(result["pace_state"], "regressing")

    def test_on_pace_forecasts_an_arrival_date_not_a_value(self):
        """Extrapolating the value gave "lands at -58 bottles a month" --
        arithmetic with no model of the world behind it."""
        result = initiatives.pace(
            self.dated("2026-09-19 00:00:00", "2027-03-19"), 50.0, now=NOW
        )
        self.assertIsNotNone(result["projected_completion"])
        self.assertIsNone(result["projected_value"])
        self.assertTrue(result["projected_hits_target"])

    def test_off_pace_forecasts_where_the_deadline_finds_you(self):
        result = initiatives.pace(
            self.dated("2026-07-21 00:00:00", "2026-11-19"), 20.0, now=NOW
        )
        self.assertFalse(result["projected_hits_target"])
        self.assertIsNotNone(result["projected_value"])

    def test_a_projected_value_never_goes_below_zero(self):
        """A count, a cost and a mass all bottom out at zero whatever the
        algebra says."""
        result = initiatives.pace(
            self.dated("2026-10-05 00:00:00", "2028-10-05"), 60.0, now=NOW
        )
        if result["projected_value"] is not None:
            self.assertGreaterEqual(result["projected_value"], 0.0)

    def test_a_projected_rate_stays_inside_a_hundred_percent(self):
        rate = self.dated("2026-07-21 00:00:00", "2026-11-19",
                          metric="diversion_rate", direction="increase",
                          baseline_value=57.0, target_value=75.0)
        result = initiatives.pace(rate, 20.0, now=NOW)
        if result["projected_value"] is not None:
            self.assertLessEqual(result["projected_value"], 100.0)

    def test_elapsed_is_reported_so_the_reader_can_judge_for_themselves(self):
        result = initiatives.pace(
            self.dated("2026-08-20 00:00:00", "2026-12-19"), 50.0, now=NOW
        )
        self.assertAlmostEqual(result["elapsed_percent"], 50.0, delta=2.0)


class HorizonRollupTests(unittest.TestCase):
    def listing(self, rows):
        with mock.patch.object(initiatives.db, "list_initiatives", return_value=list(rows)), \
             mock.patch.object(initiatives.db, "list_projects", return_value=[]), \
             mock.patch.object(initiatives.db, "list_buildings", return_value=[]), \
             mock.patch.object(initiatives, "measure", return_value=70.0):
            return initiatives.list_resolved(now=NOW)

    def test_undated_goals_are_collected_for_the_nudge(self):
        result = self.listing([goal(target_date=None)])
        self.assertEqual(len(result["undated"]), 1)

    def test_goals_that_will_not_land_are_collected(self):
        result = self.listing([
            goal(initiative_id=1, baseline_captured_at="2026-07-21 00:00:00",
                 target_date="2026-11-19", baseline_value=100.0, target_value=10.0),
        ])
        self.assertEqual(len(result["behind_pace"]), 1)

    def test_the_note_explains_that_figures_are_rates(self):
        """Without the period, "381 items" reads as a running total."""
        self.assertIn("per 30 days", self.listing([])["note"])


if __name__ == "__main__":
    unittest.main()
