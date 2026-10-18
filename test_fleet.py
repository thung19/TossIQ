"""Unit tests for fleet.py's status and fill derivation.

Pure functions over fabricated can rows -- no live OCI connection, same style
as test_insights.py, so these run without credentials. The thresholds and the
severity ordering are the part most likely to be changed later, and they are
the part a map pin's colour depends on, so they are pinned here rather than
only exercised through the API.
"""

import importlib
import os
import unittest
from datetime import datetime, timedelta
from unittest import mock

import fleet

NOW = datetime(2026, 10, 17, 12, 0, 0)


def can_row(**overrides) -> dict:
    """A healthy, freshly reporting simulated can; override one field per test."""
    row = {
        "can_id": 1,
        "can_code": "VU-TEST-01",
        "is_simulated": 1,
        "capacity_items": 320,
        "events_since_emptied": 0,
        "reported_at": NOW - timedelta(minutes=5),
        "fill_percent": 12.0,
        "camera_ok": 1,
        "actuator_ok": 1,
        "connectivity_ok": 1,
        "fault_code": None,
        "fault_detail": None,
    }
    row.update(overrides)
    return row


class ThresholdEnvTests(unittest.TestCase):
    """.env.example ships both keys with empty values, so an empty string must
    read as "not configured" rather than aborting the import that every API
    route depends on."""

    def tearDown(self):
        importlib.reload(fleet)

    def reload_with(self, env):
        with mock.patch.dict(os.environ, env):
            importlib.reload(fleet)

    def test_empty_stale_minutes_falls_back_to_the_default(self):
        self.reload_with({"FLEET_STALE_MINUTES": ""})
        self.assertEqual(fleet.STALE_MINUTES, 90)

    def test_empty_service_threshold_falls_back_to_the_default(self):
        self.reload_with({"FLEET_SERVICE_THRESHOLD_PERCENT": ""})
        self.assertEqual(fleet.SERVICE_THRESHOLD_PERCENT, 80.0)


class ResolveStatusTests(unittest.TestCase):
    def status_of(self, row, fill_percent=None):
        return fleet.resolve_status(row, fill_percent=fill_percent, now=NOW)

    def test_healthy_can_is_ok_with_no_reasons(self):
        result = self.status_of(can_row(), fill_percent=12.0)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["reasons"], [])

    def test_can_that_never_reported_is_offline(self):
        result = self.status_of(can_row(reported_at=None))
        self.assertEqual(result["status"], "offline")
        self.assertIn("no telemetry", result["reasons"][0].lower())

    def test_reading_older_than_staleness_limit_is_offline(self):
        stale = NOW - timedelta(minutes=fleet.STALE_MINUTES + 1)
        result = self.status_of(can_row(reported_at=stale))
        self.assertEqual(result["status"], "offline")
        self.assertIn("staleness limit", result["reasons"][0])

    def test_reading_just_inside_staleness_limit_is_not_offline(self):
        fresh = NOW - timedelta(minutes=fleet.STALE_MINUTES - 1)
        result = self.status_of(can_row(reported_at=fresh))
        self.assertEqual(result["status"], "ok")

    def test_unit_reporting_its_uplink_down_is_offline(self):
        result = self.status_of(can_row(connectivity_ok=0))
        self.assertEqual(result["status"], "offline")
        self.assertIn("uplink", result["reasons"][0])

    def test_camera_down_is_a_fault(self):
        result = self.status_of(can_row(camera_ok=0))
        self.assertEqual(result["status"], "fault")
        self.assertIn("Camera", result["reasons"][0])

    def test_actuator_down_is_a_fault(self):
        result = self.status_of(can_row(actuator_ok=0))
        self.assertEqual(result["status"], "fault")
        self.assertIn("actuator", result["reasons"][0])

    def test_fault_code_alone_is_a_fault_and_its_detail_is_reported(self):
        result = self.status_of(can_row(fault_code="ACT_STALL", fault_detail="Diverter flap stalled"))
        self.assertEqual(result["status"], "fault")
        self.assertIn("ACT_STALL", result["reasons"][0])
        self.assertIn("Diverter flap stalled", result["reasons"][0])

    def test_fault_code_without_detail_still_reports_the_code(self):
        result = self.status_of(can_row(fault_code="CAM_TIMEOUT"))
        self.assertEqual(result["reasons"], ["Hardware fault CAM_TIMEOUT"])

    def test_fill_at_or_over_threshold_needs_service(self):
        result = self.status_of(can_row(), fill_percent=fleet.SERVICE_THRESHOLD_PERCENT)
        self.assertEqual(result["status"], "needs_service")
        self.assertIn("service threshold", result["reasons"][0])

    def test_fill_just_under_threshold_is_ok(self):
        result = self.status_of(can_row(), fill_percent=fleet.SERVICE_THRESHOLD_PERCENT - 0.1)
        self.assertEqual(result["status"], "ok")

    def test_unknown_fill_never_needs_service(self):
        result = self.status_of(can_row(), fill_percent=None)
        self.assertEqual(result["status"], "ok")

    def test_thresholds_are_overridable_per_call(self):
        result = fleet.resolve_status(can_row(), fill_percent=50.0, now=NOW, service_threshold=40.0)
        self.assertEqual(result["status"], "needs_service")


class SeverityOrderingTests(unittest.TestCase):
    def test_offline_outranks_fault_and_needs_service(self):
        row = can_row(reported_at=None, camera_ok=0)
        result = fleet.resolve_status(row, fill_percent=95.0, now=NOW)
        self.assertEqual(result["status"], "offline")

    def test_fault_outranks_needs_service(self):
        result = fleet.resolve_status(can_row(camera_ok=0), fill_percent=95.0, now=NOW)
        self.assertEqual(result["status"], "fault")

    def test_every_reason_is_reported_worst_first(self):
        row = can_row(connectivity_ok=0, camera_ok=0, actuator_ok=0)
        result = fleet.resolve_status(row, fill_percent=95.0, now=NOW)
        self.assertEqual(result["status"], "offline")
        self.assertEqual(len(result["reasons"]), 4)
        self.assertIn("uplink", result["reasons"][0])
        self.assertIn("service threshold", result["reasons"][-1])

    def test_severity_table_orders_offline_above_fault_above_needs_service_above_ok(self):
        order = sorted(fleet.STATUS_SEVERITY, key=fleet.STATUS_SEVERITY.get, reverse=True)
        self.assertEqual(order, ["offline", "fault", "needs_service", "ok"])


class DerivedFillTests(unittest.TestCase):
    def test_fill_is_events_over_item_capacity(self):
        self.assertEqual(fleet.derived_fill_percent(80, 320), 25.0)

    def test_no_attributable_events_yields_no_fill_rather_than_zero(self):
        # With no weight sensor, nothing counted means nothing is known about
        # the can's fullness -- 0% would be a claim the system cannot make.
        self.assertIsNone(fleet.derived_fill_percent(0, 320))

    def test_fill_is_capped_at_one_hundred(self):
        self.assertEqual(fleet.derived_fill_percent(900, 320), 100.0)

    def test_unknown_item_capacity_yields_no_fill_rather_than_a_guess(self):
        self.assertIsNone(fleet.derived_fill_percent(80, None))
        self.assertIsNone(fleet.derived_fill_percent(80, 0))


class ResolveFillTests(unittest.TestCase):
    def test_simulated_can_carries_its_seeded_reading_and_says_so(self):
        fill, source = fleet.resolve_fill(can_row(is_simulated=1, fill_percent=64.0))
        self.assertEqual((fill, source), (64.0, "simulated"))

    def test_simulated_can_with_no_reading_reports_no_fill_signal(self):
        self.assertEqual(
            fleet.resolve_fill(can_row(is_simulated=1, fill_percent=None)), (None, "unknown")
        )

    def test_real_can_counts_items_and_ignores_any_seeded_value(self):
        row = can_row(is_simulated=0, fill_percent=99.0, events_since_emptied=160, capacity_items=320)
        self.assertEqual(fleet.resolve_fill(row), (50.0, "observed"))

    def test_real_can_with_unknown_capacity_reports_no_fill_signal(self):
        row = can_row(is_simulated=0, events_since_emptied=160, capacity_items=None)
        self.assertEqual(fleet.resolve_fill(row), (None, "unknown"))

    def test_real_can_with_nothing_attributed_is_not_zero_percent_observed(self):
        row = can_row(is_simulated=0, fill_percent=None, events_since_emptied=0, capacity_items=320)
        self.assertEqual(fleet.resolve_fill(row), (None, "unknown"))

    def test_observed_fill_rises_again_after_an_emptying(self):
        """An emptying resets the counting window, and disposals attributed to
        the can afterwards raise its observed fill again rather than leaving it
        pinned at a fill it never observed."""
        emptied = can_row(
            is_simulated=0, fill_percent=None, events_since_emptied=0, capacity_items=320
        )
        self.assertEqual(fleet.resolve_fill(emptied), (None, "unknown"))
        self.assertEqual(fleet.resolve_can(emptied, now=NOW)["status"], "ok")

        refilled = {**emptied, "events_since_emptied": 300}
        self.assertEqual(fleet.resolve_fill(refilled), (93.8, "observed"))
        self.assertEqual(fleet.resolve_can(refilled, now=NOW)["status"], "needs_service")


class ResolveCanTests(unittest.TestCase):
    def test_resolved_can_keeps_its_stored_columns_and_adds_the_derivation(self):
        resolved = fleet.resolve_can(can_row(fill_percent=88.0), now=NOW)
        self.assertEqual(resolved["can_code"], "VU-TEST-01")
        self.assertEqual(resolved["fill_percent"], 88.0)
        self.assertEqual(resolved["fill_source"], "simulated")
        self.assertEqual(resolved["status"], "needs_service")
        self.assertEqual(len(resolved["status_reasons"]), 1)

    def test_status_is_derived_from_the_resolved_fill_not_the_raw_reading(self):
        # A real can whose seeded reading says 99% but whose counted items say
        # 10% must not land on the service list.
        row = can_row(is_simulated=0, fill_percent=99.0, events_since_emptied=32, capacity_items=320)
        resolved = fleet.resolve_can(row, now=NOW)
        self.assertEqual(resolved["fill_percent"], 10.0)
        self.assertEqual(resolved["status"], "ok")


def cell(can_id: int, day: int, hour: int, count: int) -> dict:
    return {"can_id": can_id, "day_of_week": day, "hour_of_day": hour, "count": count}


class ActivityHeatmapTests(unittest.TestCase):
    """The shaping fleet.activity_heatmap does over db.can_activity_cells.

    db is patched out, so these run without credentials like the rest of this
    file; the SQL itself is exercised by hitting the live endpoint.
    """

    def heatmap(self, cells, **kwargs):
        with mock.patch.object(fleet.db, "can_activity_cells", return_value=cells):
            return fleet.activity_heatmap(**kwargs)

    def test_sparse_cells_are_densified_into_a_seven_by_twenty_four_grid(self):
        result = self.heatmap([cell(1, 0, 9, 3), cell(2, 0, 9, 4), cell(1, 6, 23, 1)])
        self.assertEqual(len(result["day_hour"]), 7)
        self.assertTrue(all(len(row) == 24 for row in result["day_hour"]))
        # Two cans in the same bucket sum into one campus cell.
        self.assertEqual(result["day_hour"][0][9], 7)
        self.assertEqual(result["day_hour"][6][23], 1)
        self.assertEqual(result["total_events"], 8)

    def test_per_can_totals_sum_across_every_bucket(self):
        result = self.heatmap([cell(1, 0, 9, 3), cell(1, 2, 18, 5), cell(2, 0, 9, 4)])
        self.assertEqual(result["by_can"], [{"can_id": 1, "count": 8}, {"can_id": 2, "count": 4}])
        self.assertEqual(result["max_can"], 8)

    def test_empty_window_reports_zeroes_rather_than_failing(self):
        result = self.heatmap([])
        self.assertEqual(result["total_events"], 0)
        self.assertIsNone(result["peak"])
        self.assertIsNone(result["typical_peak"])
        # A zero scale bound would make every colour lookup divide by zero.
        self.assertEqual(result["scale_max_cell"], 1)
        self.assertEqual(result["scale_max_can"], 1)

    def test_one_burst_does_not_set_the_colour_scale(self):
        """The regression this exists for: the live camera logged 294 items
        into one hour during a demo run. Scaling 168 cells against that paints
        every ordinary hour the same near-black."""
        ordinary = [cell(1, day, hour, 5) for day in range(7) for hour in range(8, 20)]
        result = self.heatmap([*ordinary, cell(2, 6, 2, 294)])
        self.assertEqual(result["max_cell"], 294)
        self.assertLess(result["scale_max_cell"], 20)

    def test_busiest_hour_is_the_recurring_one_not_the_single_largest_bucket(self):
        """6pm is busy every day; 2am is busy once. The headline figure must
        name 6pm."""
        recurring = [cell(1, day, 18, 9) for day in range(7)]
        burst = [cell(2, 6, 2, 250)]
        result = self.heatmap([*recurring, *burst])
        self.assertEqual(result["typical_peak"]["hour_of_day"], 18)
        # The absolute peak is still reported -- as an outlier, not as the answer.
        self.assertEqual(result["peak"]["hour_of_day"], 2)
        self.assertEqual(result["peak"]["count"], 250)

    def test_typical_hour_ignores_an_hour_busy_on_a_minority_of_days(self):
        # 10am is enormous on two days and dead on five; 15:00 is steady.
        spiky = [cell(1, 0, 10, 80), cell(1, 1, 10, 80)]
        steady = [cell(1, day, 15, 4) for day in range(7)]
        result = self.heatmap([*spiky, *steady])
        self.assertEqual(result["typical_peak"]["hour_of_day"], 15)

    def test_day_names_are_monday_first_matching_the_iso_week_sql(self):
        result = self.heatmap([cell(1, 0, 9, 1)])
        self.assertEqual(result["day_names"][0], "Mon")
        self.assertEqual(result["day_names"][6], "Sun")

    def test_window_days_is_passed_through_to_the_query_and_echoed_back(self):
        with mock.patch.object(fleet.db, "can_activity_cells", return_value=[]) as query:
            result = fleet.activity_heatmap(days=30, building_id=4, model_id=2)
        query.assert_called_once_with(days=30, building_id=4, model_id=2)
        self.assertEqual(result["window_days"], 30)


class ActivityBucketTests(unittest.TestCase):
    """fleet.activity_for_bucket is the reference the frontend's identical
    client-side slice (canCountsForBucket in lib/api.ts) is checked against."""

    CELLS = [
        cell(1, 4, 18, 3),
        cell(1, 4, 9, 2),
        cell(1, 0, 18, 5),
        cell(2, 4, 18, 7),
    ]

    def test_both_coordinates_selects_one_bucket(self):
        self.assertEqual(fleet.activity_for_bucket(self.CELLS, day_of_week=4, hour_of_day=18), {1: 3, 2: 7})

    def test_day_alone_selects_the_whole_day(self):
        self.assertEqual(fleet.activity_for_bucket(self.CELLS, day_of_week=4), {1: 5, 2: 7})

    def test_hour_alone_selects_that_hour_across_the_week(self):
        self.assertEqual(fleet.activity_for_bucket(self.CELLS, hour_of_day=18), {1: 8, 2: 7})

    def test_neither_coordinate_selects_the_whole_window(self):
        self.assertEqual(fleet.activity_for_bucket(self.CELLS), {1: 10, 2: 7})

    def test_a_bucket_nothing_falls_into_is_empty_not_an_error(self):
        self.assertEqual(fleet.activity_for_bucket(self.CELLS, day_of_week=2, hour_of_day=3), {})


class PercentileAndMedianTests(unittest.TestCase):
    def test_percentile_of_an_empty_list_is_one_not_zero(self):
        self.assertEqual(fleet._percentile([], 0.95), 1)

    def test_percentile_is_nearest_rank_and_never_below_one(self):
        self.assertEqual(fleet._percentile([0, 0, 0], 0.95), 1)
        # Rank interpolated across the index range: round(0.95 * 99) = 94,
        # so the 95th percentile of 1..100 is the 95th value.
        self.assertEqual(fleet._percentile(list(range(1, 101)), 0.95), 95)
        self.assertEqual(fleet._percentile(list(range(1, 101)), 0.0), 1)
        self.assertEqual(fleet._percentile(list(range(1, 101)), 1.0), 100)

    def test_median_takes_the_lower_middle_rather_than_averaging(self):
        self.assertEqual(fleet._median([1, 2, 3, 4]), 2)
        self.assertEqual(fleet._median([5]), 5)
        self.assertEqual(fleet._median([]), 0)


if __name__ == "__main__":
    unittest.main()
