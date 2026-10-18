"""Unit tests for hazards.py: classification and alerting.

Pure functions and a patched db, so no OCI connection. What these guard is
the part a safety feature cannot get wrong: a hazard that classifies as
something milder than it is, or one the system quietly drops because it
matched nothing.
"""

import unittest
from datetime import datetime, timedelta
from unittest import mock

import hazards

NOW = datetime(2026, 10, 19, 12, 0, 0)


def stamp(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%d %H:%M:%S")


def flagged(**overrides) -> dict:
    row = {
        "event_id": 1,
        "detected_object": "disposable vape",
        "hazard_reason": "Sealed lithium cell visible",
        "hazard_class": "vape",
        "hazard_severity": "critical",
        "building_name": "Branscomb Quad",
        "can_code": "VU-BRANSCOMB-02",
        "created_at": stamp(1),
    }
    row.update(overrides)
    return row


class ClassificationTests(unittest.TestCase):
    def test_a_vape_is_critical(self):
        verdict = hazards.classify("disposable vape", None)
        self.assertEqual(verdict["hazard_class"], "vape")
        self.assertEqual(verdict["severity"], "critical")

    def test_a_rechargeable_cell_is_lithium_not_alkaline(self):
        """Ordering matters: "lithium battery" contains "battery", and the
        milder class must not win."""
        self.assertEqual(hazards.classify("power bank", None)["hazard_class"], "lithium_battery")
        self.assertEqual(
            hazards.classify("laptop battery", None)["hazard_class"], "lithium_battery"
        )

    def test_a_plain_cell_is_alkaline(self):
        self.assertEqual(hazards.classify("AA battery", None)["hazard_class"], "alkaline_battery")

    def test_an_aerosol_is_not_filed_as_a_gas_cylinder(self):
        """The regression this exists for: the model writes "pressurised"
        in the reason for any can under pressure, and matching on that word
        filed every deodorant aerosol as a propane cylinder."""
        verdict = hazards.classify("aerosol can", "Pressurised can with a flammable symbol")
        self.assertEqual(verdict["hazard_class"], "aerosol")

    def test_a_real_cylinder_still_classifies_as_one(self):
        self.assertEqual(
            hazards.classify("butane canister", None)["hazard_class"], "pressurised"
        )

    def test_the_reason_can_carry_the_evidence_the_label_lacks(self):
        """The label says "small device", the reason says what was wrong
        with it. Either alone would miss cases the other catches."""
        verdict = hazards.classify("small device", "Visible battery compartment")
        self.assertEqual(verdict["hazard_class"], "alkaline_battery")

    def test_an_unrecognised_hazard_says_so_rather_than_guessing(self):
        """A hazard quietly filed as an alkaline battery is handled as an
        alkaline battery. One that announces itself as unknown is inspected."""
        verdict = hazards.classify("unidentified container", "Corroded cap, contents unknown")
        self.assertEqual(verdict["hazard_class"], "unclassified")
        self.assertIn("Inspect", verdict["handling"])

    def test_nothing_to_match_on_is_unclassified(self):
        self.assertEqual(hazards.classify(None, None)["hazard_class"], "unclassified")
        self.assertEqual(hazards.classify("", "")["hazard_class"], "unclassified")

    def test_matching_is_case_insensitive(self):
        self.assertEqual(hazards.classify("Disposable VAPE", None)["hazard_class"], "vape")

    def test_every_class_carries_handling_and_a_name(self):
        for hazard_class, severity, display, keywords, handling in hazards.HAZARD_TAXONOMY:
            self.assertTrue(display, hazard_class)
            self.assertTrue(keywords, hazard_class)
            self.assertGreater(len(handling), 40, hazard_class)
            self.assertIn(severity, hazards.SEVERITY_ORDER, hazard_class)

    def test_every_severity_has_a_response_window(self):
        for _class, severity, *_rest in hazards.HAZARD_TAXONOMY:
            self.assertIn(severity, hazards.RESPONSE_HOURS)

    def test_fire_and_injury_risks_are_the_critical_ones(self):
        """Severity is about response time, not unpleasantness. Anything
        that can combust in a compacted load or cut a handler is critical."""
        for label in ("disposable vape", "power bank", "syringe", "fluorescent tube"):
            self.assertEqual(hazards.classify(label, None)["severity"], "critical", label)
        for label in ("AA battery", "aerosol can", "pill bottle"):
            self.assertEqual(hazards.classify(label, None)["severity"], "high", label)

    def test_lookups_agree_with_classification(self):
        verdict = hazards.classify("syringe", None)
        self.assertEqual(hazards.display_name("sharps"), verdict["display_name"])
        self.assertEqual(hazards.handling_for("sharps"), verdict["handling"])
        self.assertEqual(hazards.severity_for("sharps"), verdict["severity"])

    def test_an_unknown_class_lookup_falls_back_rather_than_raising(self):
        self.assertEqual(hazards.severity_for("nonsense"), "unclassified")
        self.assertIn("Inspect", hazards.handling_for(None))


class SummaryTests(unittest.TestCase):
    def summary(self, outstanding=(), by_class=(), by_location=()):
        with mock.patch.object(hazards.db, "list_hazard_disposals",
                               return_value=list(outstanding)), \
             mock.patch.object(hazards.db, "hazard_class_counts", return_value=list(by_class)), \
             mock.patch.object(hazards.db, "hazard_location_counts",
                               return_value=list(by_location)), \
             mock.patch.object(hazards.db, "hazard_trend", return_value=[]):
            return hazards.summary(days=30, now=NOW)

    def test_a_critical_hazard_is_overdue_after_four_hours(self):
        result = self.summary(outstanding=[flagged(created_at=stamp(5))])
        self.assertEqual(len(result["overdue"]), 1)
        self.assertAlmostEqual(result["overdue"][0]["hours_overdue"], 1.0, places=1)

    def test_a_fresh_critical_hazard_is_not_overdue(self):
        self.assertEqual(self.summary(outstanding=[flagged(created_at=stamp(2))])["overdue"], [])

    def test_the_window_follows_the_severity(self):
        """A medium hazard open for six hours is fine; a critical one is
        not. One threshold for both would either cry wolf or miss fires."""
        medium = flagged(hazard_severity="medium", created_at=stamp(6))
        critical = flagged(event_id=2, created_at=stamp(6))
        result = self.summary(outstanding=[medium, critical])
        self.assertEqual([row["event_id"] for row in result["overdue"]], [2])

    def test_overdue_is_sorted_worst_and_latest_first(self):
        result = self.summary(outstanding=[
            flagged(event_id=1, hazard_severity="high", created_at=stamp(100)),
            flagged(event_id=2, created_at=stamp(10)),
            flagged(event_id=3, created_at=stamp(300)),
        ])
        self.assertEqual([row["event_id"] for row in result["overdue"]], [3, 2, 1])

    def test_a_repeated_hazard_in_one_building_becomes_a_recurrence(self):
        result = self.summary(by_location=[
            {"building_name": "Branscomb Quad", "building_id": 1, "hazard_class": "vape",
             "severity": "critical", "count": 4, "cans": 2, "last_seen": stamp(2)},
        ])
        self.assertEqual(len(result["recurring"]), 1)
        self.assertIn("collection point", result["recurring"][0]["handling"] + " collection point")

    def test_a_one_off_is_not_a_recurrence(self):
        result = self.summary(by_location=[
            {"building_name": "Rand Hall", "building_id": 2, "hazard_class": "sharps",
             "severity": "critical", "count": 1, "cans": 1, "last_seen": stamp(2)},
        ])
        self.assertEqual(result["recurring"], [])

    def test_unattributed_bins_cannot_be_a_location_pattern(self):
        """"Unattributed" is not a place anybody can go and put a sign on."""
        result = self.summary(by_location=[
            {"building_name": "unattributed", "building_id": None, "hazard_class": "vape",
             "severity": "critical", "count": 9, "cans": 1, "last_seen": stamp(2)},
        ])
        self.assertEqual(result["recurring"], [])

    def test_severity_totals_roll_up_across_classes(self):
        result = self.summary(by_class=[
            {"hazard_class": "vape", "severity": "critical", "count": 7, "outstanding": 5},
            {"hazard_class": "sharps", "severity": "critical", "count": 2, "outstanding": 1},
            {"hazard_class": "aerosol", "severity": "high", "count": 4, "outstanding": 0},
        ])
        critical = next(r for r in result["by_severity"] if r["severity"] == "critical")
        self.assertEqual((critical["count"], critical["outstanding"]), (9, 6))
        self.assertEqual(result["total"], 13)

    def test_severities_are_listed_worst_first(self):
        result = self.summary(by_class=[
            {"hazard_class": "e_waste", "severity": "medium", "count": 1, "outstanding": 1},
            {"hazard_class": "vape", "severity": "critical", "count": 1, "outstanding": 1},
            {"hazard_class": "aerosol", "severity": "high", "count": 1, "outstanding": 1},
        ])
        self.assertEqual([r["severity"] for r in result["by_severity"]],
                         ["critical", "high", "medium"])

    def test_an_empty_window_reports_nothing_rather_than_failing(self):
        result = self.summary()
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["overdue"], [])
        self.assertEqual(result["recurring"], [])

    def test_classes_are_served_with_their_handling(self):
        """The procedure has to travel with the count, or the page shows a
        number nobody can act on."""
        result = self.summary(by_class=[
            {"hazard_class": "sharps", "severity": "critical", "count": 2, "outstanding": 2},
        ])
        self.assertIn("sharps container", result["by_class"][0]["handling"])


if __name__ == "__main__":
    unittest.main()
