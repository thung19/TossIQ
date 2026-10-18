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


if __name__ == "__main__":
    unittest.main()
