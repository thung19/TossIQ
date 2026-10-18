"""Unit tests for impact.py's emission arithmetic.

No database, no network. What these guard is the direction of the
arithmetic: a switch that is worse must come out negative, so the engine
declines to recommend it rather than cheerleading a change that makes
things worse.
"""

import unittest

import impact


def item(**overrides) -> dict:
    row = {
        "material": "plastic", "material_subtype": "PET",
        "unit_weight_grams": 12.0, "disposal_category": "recycling",
        "expected_uses": 1,
    }
    row.update(overrides)
    return row


class FactorTests(unittest.TestCase):
    def test_a_subtype_beats_its_material_family(self):
        """Aluminium is an order above steel; both are "metal"."""
        self.assertEqual(impact.embodied_factor("metal", "aluminium"), 9.0)
        self.assertEqual(impact.embodied_factor("metal", "tinplate steel"), 2.0)

    def test_an_unknown_subtype_falls_back_to_the_family(self):
        self.assertEqual(
            impact.embodied_factor("paper", "some unlisted grade"),
            impact.EMBODIED_CO2E_PER_KG["paper"],
        )

    def test_an_unknown_material_scores_zero_rather_than_a_guess(self):
        """A missing factor must make a recommendation look smaller than it
        is, never larger."""
        self.assertEqual(impact.embodied_factor("unobtanium", None), 0.0)
        self.assertEqual(impact.embodied_factor(None, None), 0.0)

    def test_food_carries_the_heaviest_factor_of_the_common_materials(self):
        """Its footprint is the farming behind it, spent before it reaches
        the tray -- which is why food waste dominates on carbon."""
        food = impact.EMBODIED_CO2E_BY_SUBTYPE["edible food"]
        self.assertGreater(food, impact.EMBODIED_CO2E_PER_KG["paper"])
        self.assertGreater(food, impact.EMBODIED_CO2E_PER_KG["plastic"])

    def test_residue_scores_far_below_edible_food(self):
        """A peel is evidence the fruit was eaten, not a loss."""
        self.assertLess(
            impact.EMBODIED_CO2E_BY_SUBTYPE["fruit residue"],
            impact.EMBODIED_CO2E_BY_SUBTYPE["edible food"],
        )


class AvoidedProductionTests(unittest.TestCase):
    def test_carbon_scales_with_mass_and_units(self):
        one = impact.avoided_production_co2e(item(), 1)
        hundred = impact.avoided_production_co2e(item(), 100)
        self.assertAlmostEqual(hundred, one * 100, places=6)

    def test_a_product_with_no_mass_contributes_nothing(self):
        self.assertEqual(impact.avoided_production_co2e(item(unit_weight_grams=None), 100), 0.0)


class DiversionTests(unittest.TestCase):
    def test_compost_beats_recycling_for_avoided_landfill_methane(self):
        self.assertGreater(impact.diversion_co2e(1000, "compost"),
                           impact.diversion_co2e(1000, "recycling"))

    def test_landfill_earns_no_diversion_credit(self):
        self.assertEqual(impact.diversion_co2e(1000, "landfill"), 0.0)

    def test_an_unknown_stream_earns_nothing(self):
        self.assertEqual(impact.diversion_co2e(1000, None), 0.0)


class SwitchTests(unittest.TestCase):
    def test_a_reusable_produces_far_fewer_units(self):
        disposable = item(unit_weight_grams=12.0)
        flask = item(material="metal", material_subtype=None, unit_weight_grams=290.0,
                     expected_uses=1200)
        result = impact.switch_co2e(disposable, flask, 1200)
        self.assertEqual(result["units_avoided"], 1199)
        self.assertGreater(result["production_saved_kg"], 0)

    def test_a_heavier_replacement_can_be_worse_and_is_reported_as_such(self):
        """Foam cup to paper cup: four times the mass, both to landfill. The
        arithmetic has to come out negative so the engine declines it."""
        foam = item(material="plastic", material_subtype="EPS",
                    unit_weight_grams=2.6, disposal_category="landfill")
        paper = item(material="paper", material_subtype=None,
                     unit_weight_grams=11.0, disposal_category="landfill")
        result = impact.switch_co2e(foam, paper, 1000)
        self.assertLess(result["net_co2e_kg"], 0)

    def test_production_and_diversion_are_reported_apart(self):
        """A switch can be worse on production and better on disposal. One
        net number would hide the trade rather than show it."""
        result = impact.switch_co2e(item(), item(disposal_category="compost"), 100)
        self.assertIn("production_saved_kg", result)
        self.assertIn("diversion_gained_kg", result)

    def test_landfill_avoided_counts_only_what_leaves_landfill(self):
        landfilled = item(disposal_category="landfill", unit_weight_grams=10.0)
        composted = item(disposal_category="compost", unit_weight_grams=10.0)
        result = impact.switch_co2e(landfilled, composted, 1000)
        self.assertAlmostEqual(result["landfill_avoided_kg"], 10.0, places=1)

    def test_a_switch_between_two_landfilled_items_avoids_no_landfill(self):
        a = item(disposal_category="landfill", unit_weight_grams=10.0)
        b = item(disposal_category="landfill", unit_weight_grams=10.0)
        self.assertEqual(impact.switch_co2e(a, b, 1000)["landfill_avoided_kg"], 0.0)


class DescribeTests(unittest.TestCase):
    def test_tonnes_above_a_tonne_kilograms_below(self):
        self.assertEqual(impact.describe_co2e(23.4), "23 kg CO2e")
        self.assertEqual(impact.describe_co2e(1450), "1.4 t CO2e")

    def test_the_disclaimer_names_the_factors_as_unverified(self):
        """These are illustrative values, and anything built on them has to
        say so before it leaves the building."""
        self.assertIn("LCA", impact.DISCLAIMER)


if __name__ == "__main__":
    unittest.main()
