"""Unit tests for insights.py's recommendation rules.

Mocks db.py's query functions directly (plain stdlib unittest.mock, no live
OCI connection, same style as test_genai_vision.py) so these run without
credentials.
"""

import unittest
from unittest import mock

import insights


class HazardFlagRecommendationsTests(unittest.TestCase):
    @mock.patch("insights.db.list_hazard_events")
    def test_recommendation_references_object_location_date_and_reason(self, mock_list_hazard_events):
        mock_list_hazard_events.return_value = [
            {
                "detected_object": "AA battery",
                "location": "Building 3 kitchen",
                "hazard_reason": "visible battery compartment",
                "date": "2026-10-15",
            }
        ]

        out = insights._hazard_flag_recommendations(days=30)

        self.assertEqual(len(out), 1)
        text = out[0]
        self.assertIn("AA battery", text)
        self.assertIn("Building 3 kitchen", text)
        self.assertIn("2026-10-15", text)
        self.assertIn("visible battery compartment", text)
        self.assertIn("manual inspection", text)
        mock_list_hazard_events.assert_called_once_with(days=30)

    @mock.patch("insights.db.list_hazard_events")
    def test_no_hazard_events_produces_no_recommendations(self, mock_list_hazard_events):
        mock_list_hazard_events.return_value = []

        out = insights._hazard_flag_recommendations(days=30)

        self.assertEqual(out, [])

    @mock.patch("insights.db.list_hazard_events")
    def test_multiple_hazard_events_each_produce_a_recommendation(self, mock_list_hazard_events):
        mock_list_hazard_events.return_value = [
            {
                "detected_object": "AA battery",
                "location": "Building 3 kitchen",
                "hazard_reason": "visible battery compartment",
                "date": "2026-10-15",
            },
            {
                "detected_object": "cleaning spray bottle",
                "location": "unspecified",
                "hazard_reason": "chemical hazard warning symbol visible",
                "date": "2026-10-16",
            },
        ]

        out = insights._hazard_flag_recommendations(days=30)

        self.assertEqual(len(out), 2)
        self.assertIn("cleaning spray bottle", out[1])
        self.assertIn("chemical hazard warning symbol visible", out[1])


if __name__ == "__main__":
    unittest.main()
