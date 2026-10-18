"""Unit tests for recommendations.py.

Rules are run against a hand-built context with db and fleet patched out, so
these need no OCI connection. What they mostly guard is restraint: these
rules make claims about money and rotas, and the failure mode that matters
is a rule firing on four observations, or projecting a saving that is not
there, or burying the page in near-identical cards.
"""

import unittest
from unittest import mock

import recommendations as rec


def product(**overrides) -> dict:
    row = {
        "product_id": 1, "sku": "DISP-CUP-H12", "product_name": "Paper Hot Cup 12 oz",
        "brand": None, "variant_label": None, "supplier": "Imperial Dade",
        "detected_as": "cup", "material": "paper", "material_subtype": "paperboard",
        "unit_cost": 0.11, "unit_weight_grams": 11.0, "disposal_category": "landfill",
        "recyclable": 0, "reusable": 0, "case_pack_qty": 1000, "case_cost": 94.0,
        "active": 1, "substitute_sku": "REU-MUG-CER12", "substitute_note": "note",
        "expected_uses": 1,
    }
    row.update(overrides)
    return row


def reusable(**overrides) -> dict:
    return product(**{
        "product_id": 2, "sku": "REU-MUG-CER12", "product_name": "Ceramic Mug 12 oz",
        "unit_cost": 4.20, "reusable": 1, "expected_uses": 500,
        "substitute_sku": None, "detected_as": None, **overrides,
    })


def sku_row(bucket: str, n: int) -> dict:
    return {"bucket": bucket, "n": n, "matched_n": n, "matched_cost": 0.0,
            "matched_grams": 0.0, "class_cost": 0.0, "class_grams": 0.0,
            "no_cost_n": 0, "avg_confidence": 80.0}


def can(**overrides) -> dict:
    row = {
        "can_id": 1, "can_code": "VU-RAND-01", "building_name": "Rand Hall",
        "fill_percent": 20.0, "fill_source": "simulated", "status": "ok",
        "events_since_emptied": 10, "last_emptied_at": "2026-10-01 08:00:00",
    }
    row.update(overrides)
    return row


def context(**overrides) -> dict:
    base = {
        "days": 30,
        "products": {},
        "fleet": [],
        "by_sku": [],
        "by_can": [],
        "activity": {"window_days": 30, "cells": []},
        "edible_food": [],
        "misrouted": [],
    }
    base.update(overrides)
    return base


class ReusableSwitchTests(unittest.TestCase):
    def ctx(self, count: int, **product_overrides):
        return context(
            products={"DISP-CUP-H12": product(**product_overrides),
                      "REU-MUG-CER12": reusable()},
            by_sku=[sku_row("DISP-CUP-H12", count)],
        )

    def test_a_volume_switch_is_recommended_with_payback_evidence(self):
        out = rec.switch_to_reusable(self.ctx(600))
        self.assertEqual(len(out), 1)
        self.assertGreater(out[0]["annual_saving"], 0)
        labels = [block["label"] for block in out[0]["evidence"]]
        self.assertIn("Cost per use", labels)
        self.assertIn("Payback", labels)

    def test_a_handful_of_items_is_not_enough_to_recommend_capital_spend(self):
        """The failure mode worth guarding: four cups in a month becoming
        'buy 400 mugs'."""
        self.assertEqual(rec.switch_to_reusable(self.ctx(rec.MIN_OBSERVATIONS - 1)), [])

    def test_the_switch_is_skipped_when_the_reusable_costs_more_per_use(self):
        """A reusable rated for three uses is not a saving, and the rule has
        to notice rather than recommending it on principle."""
        ctx = self.ctx(600)
        ctx["products"]["REU-MUG-CER12"] = reusable(expected_uses=3)
        self.assertEqual(rec.switch_to_reusable(ctx), [])

    def test_a_product_with_no_declared_substitute_is_left_alone(self):
        ctx = self.ctx(600, substitute_sku=None)
        self.assertEqual(rec.switch_to_reusable(ctx), [])

    def test_a_substitute_that_is_not_reusable_is_not_a_reuse_recommendation(self):
        ctx = self.ctx(600)
        ctx["products"]["REU-MUG-CER12"] = reusable(reusable=0)
        self.assertEqual(rec.switch_to_reusable(ctx), [])

    def test_the_washing_assumption_is_named_in_the_caveat(self):
        """It is the only figure in the arithmetic with no source in the
        data, so it cannot be left implicit."""
        out = rec.switch_to_reusable(self.ctx(600))
        self.assertIn("ashing", out[0]["caveat"])

    def test_saving_scales_with_the_window(self):
        thirty = rec.switch_to_reusable(self.ctx(600))[0]["annual_saving"]
        ctx = self.ctx(600)
        ctx["days"] = 60
        sixty = rec.switch_to_reusable(ctx)[0]["annual_saving"]
        self.assertAlmostEqual(thirty, sixty * 2, delta=thirty * 0.02)


class CapacityTests(unittest.TestCase):
    def ctx(self, per_can: dict[str, int]):
        cans = [can(can_id=index, can_code=code,
                    building_name="Busy Hall" if code.startswith("B") else "Quiet Hall")
                for index, code in enumerate(per_can, start=1)]
        return context(
            fleet=cans,
            by_can=[sku_row(code, count) for code, count in per_can.items()],
        )

    def test_a_building_whose_typical_can_is_overloaded_is_flagged(self):
        out = rec.add_or_relocate_cans(self.ctx({
            "B1": 100, "B2": 90, "B3": 95,
            "Q1": 20, "Q2": 18, "Q3": 22,
        }))
        self.assertEqual([item["title"] for item in out], ["Add a bin at Busy Hall"])

    def test_one_busy_can_does_not_carry_a_building(self):
        """The regression this exists for: the live camera logged a 294-item
        burst into one library can, and a totals-based rule would have
        recommended hardware for a building with one popular bin."""
        out = rec.add_or_relocate_cans(self.ctx({
            "B1": 400, "B2": 12, "B3": 10,
            "Q1": 20, "Q2": 18, "Q3": 22,
        }))
        self.assertEqual(out, [])

    def test_a_building_with_too_little_data_is_skipped(self):
        out = rec.add_or_relocate_cans(self.ctx({"B1": 3, "Q1": 1}))
        self.assertEqual(out, [])

    def test_evidence_shows_every_can_so_the_median_can_be_checked(self):
        out = rec.add_or_relocate_cans(self.ctx({
            "B1": 100, "B2": 90, "B3": 95, "Q1": 20, "Q2": 18, "Q3": 22,
        }))
        bars = [block for block in out[0]["evidence"] if block["type"] == "bars"][0]
        self.assertEqual(len(bars["rows"]), 3)


class RouteTimingTests(unittest.TestCase):
    def ctx(self, cans_hours: dict[str, list[int]]):
        fleet_rows, cells = [], []
        for index, (code, hours) in enumerate(cans_hours.items(), start=1):
            fleet_rows.append(can(can_id=index, can_code=code, building_name=f"Hall {index}"))
            for hour, count in enumerate(hours):
                if count:
                    cells.append({"can_id": index, "day_of_week": 0,
                                  "hour_of_day": hour, "count": count})
        return context(fleet=fleet_rows,
                       activity={"window_days": 30, "cells": cells})

    @staticmethod
    def peaked(start: int, weight: int = 10) -> list[int]:
        hours = [1] * 24
        for offset in range(5):
            hours[(start + offset) % 24] = weight
        return hours

    def test_cans_peaking_together_become_one_route_not_many_cards(self):
        """The first version emitted a card per can and produced twenty-five
        of them. Nobody re-times a single bin."""
        out = rec.retime_collections(self.ctx({
            "A": self.peaked(13), "B": self.peaked(13), "C": self.peaked(13),
        }))
        self.assertEqual(len(out), 1)
        self.assertIn("3 cans", out[0]["title"])

    def test_fewer_than_a_routes_worth_of_cans_is_not_a_route(self):
        out = rec.retime_collections(self.ctx({
            "A": self.peaked(13), "B": self.peaked(13),
        }))
        self.assertEqual(out, [])

    def test_a_can_with_no_daily_pattern_never_qualifies(self):
        flat = [5] * 24
        out = rec.retime_collections(self.ctx({"A": flat, "B": flat, "C": flat, "D": flat}))
        self.assertEqual(out, [])

    def test_a_quiet_can_is_ignored_however_concentrated(self):
        spike = [0] * 24
        spike[13] = 3
        out = rec.retime_collections(self.ctx({"A": spike, "B": spike, "C": spike}))
        self.assertEqual(out, [])

    def test_pickup_snaps_to_a_rosterable_slot(self):
        out = rec.retime_collections(self.ctx({
            "A": self.peaked(13), "B": self.peaked(13), "C": self.peaked(13),
        }))
        slot = out[0]["key"].split(":")[1]
        self.assertIn(int(slot), rec.COLLECTION_SLOTS)


class NearestSlotTests(unittest.TestCase):
    def test_an_ideal_hour_snaps_to_the_closest_slot(self):
        self.assertEqual(rec._nearest_slot(12), 11)
        self.assertEqual(rec._nearest_slot(18), 19)

    def test_the_clock_wraps_so_late_night_does_not_snap_to_morning(self):
        """Measured the long way round, 11pm is 8 hours from the 7am slot and
        1 hour from the 10pm one."""
        self.assertEqual(rec._nearest_slot(23), 22)
        self.assertEqual(rec._nearest_slot(0), 22)


class FoodPortionTests(unittest.TestCase):
    def food(self, building: str, item: str, count: int, cost: float) -> dict:
        return {"building": building, "item": item, "count": count,
                "cost": cost, "grams": count * 80.0}

    def test_edible_waste_is_reported_per_building_with_a_projection(self):
        out = rec.reduce_food_portions(context(edible_food=[
            self.food("Rand Hall", "Plate Scrapings (uneaten)", 20, 9.0),
            self.food("Rand Hall", "Pizza Crust (uneaten)", 10, 1.8),
        ]))
        self.assertEqual(len(out), 1)
        self.assertIn("Rand Hall", out[0]["title"])
        # 10.80 over 30 days annualises to about 131.
        self.assertAlmostEqual(out[0]["annual_saving"], 131.4, delta=1.0)

    def test_the_worst_item_drives_the_suggested_action(self):
        out = rec.reduce_food_portions(context(edible_food=[
            self.food("Rand Hall", "Plate Scrapings (uneaten)", 20, 9.0),
            self.food("Rand Hall", "Pizza Crust (uneaten)", 10, 1.8),
        ]))
        self.assertIn("plate scrapings", out[0]["action"].lower())

    def test_a_building_with_little_waste_is_not_lectured(self):
        out = rec.reduce_food_portions(context(edible_food=[
            self.food("Rand Hall", "Pizza Crust (uneaten)", 2, 0.36),
        ]))
        self.assertEqual(out, [])

    def test_the_basis_states_that_residue_is_excluded(self):
        """Peels and spent grounds are evidence food was eaten. If the basis
        did not say they are excluded, a reader would assume otherwise."""
        out = rec.reduce_food_portions(context(edible_food=[
            self.food("Rand Hall", "Plate Scrapings (uneaten)", 20, 9.0),
        ]))
        self.assertIn("residue", out[0]["basis"])


class MisroutingTests(unittest.TestCase):
    def row(self, item: str, logged: str, should: str, count: int) -> dict:
        return {"item": item, "logged_as": logged, "should_be": should,
                "count": count, "grams": count * 20.0}

    def test_misroutes_group_by_direction_not_by_item(self):
        out = rec.fix_misrouting(context(misrouted=[
            self.row("Paper Straw", "landfill", "compost", 18),
            self.row("Fibre Clamshell", "landfill", "compost", 10),
            self.row("PET Cup", "landfill", "recycling", 13),
        ]))
        self.assertEqual(len(out), 2)

    def test_a_small_misroute_is_below_the_bar(self):
        out = rec.fix_misrouting(context(misrouted=[
            self.row("Paper Straw", "landfill", "compost", 2),
        ]))
        self.assertEqual(out, [])

    def test_the_basis_says_the_figure_is_a_floor(self):
        """Only catalog-matched items can be checked, so the true number is
        higher; claiming it as a total would overstate the coverage."""
        out = rec.fix_misrouting(context(misrouted=[
            self.row("Paper Straw", "landfill", "compost", 18),
        ]))
        self.assertIn("floor", out[0]["basis"])


class ServiceBacklogTests(unittest.TestCase):
    def test_a_cluster_of_full_cans_is_reported_with_the_worst_building(self):
        out = rec.service_backlog(context(fleet=[
            can(can_id=1, can_code="A1", building_name="Rand Hall", fill_percent=96.0),
            can(can_id=2, can_code="A2", building_name="Rand Hall", fill_percent=88.0),
            can(can_id=3, can_code="B1", building_name="Quiet Hall", fill_percent=84.0),
        ]))
        self.assertEqual(len(out), 1)
        self.assertIn("Rand Hall", out[0]["summary"])

    def test_a_single_full_can_is_a_worklist_item_not_a_recommendation(self):
        out = rec.service_backlog(context(fleet=[
            can(fill_percent=96.0),
            can(can_id=2, can_code="A2", fill_percent=10.0),
        ]))
        self.assertEqual(out, [])

    def test_a_can_with_unknown_fill_is_not_assumed_full(self):
        out = rec.service_backlog(context(fleet=[
            can(fill_percent=None), can(can_id=2, can_code="A2", fill_percent=None),
        ]))
        self.assertEqual(out, [])


class GenerateTests(unittest.TestCase):
    def test_one_failing_rule_does_not_empty_the_page(self):
        def broken(_context):
            raise RuntimeError("boom")

        with mock.patch.object(rec, "build_context", return_value=context()), \
             mock.patch.object(rec, "RULES", (broken, rec.service_backlog)):
            report = rec.generate(days=30)
        self.assertEqual(report["recommendations"], [])
        self.assertEqual(report["rules_failed"], ["broken: RuntimeError"])

    def test_money_recommendations_rank_above_ones_without(self):
        with mock.patch.object(rec, "build_context", return_value=context(
            products={"DISP-CUP-H12": product(), "REU-MUG-CER12": reusable()},
            by_sku=[sku_row("DISP-CUP-H12", 600)],
            fleet=[can(can_id=1, can_code="A1", fill_percent=96.0),
                   can(can_id=2, can_code="A2", fill_percent=88.0)],
        )):
            report = rec.generate(days=30)
        self.assertGreater(len(report["recommendations"]), 1)
        self.assertEqual(report["recommendations"][0]["kind"], "procurement")

    def test_keys_are_stable_across_runs_so_a_link_survives(self):
        ctx = context(products={"DISP-CUP-H12": product(), "REU-MUG-CER12": reusable()},
                      by_sku=[sku_row("DISP-CUP-H12", 600)])
        with mock.patch.object(rec, "build_context", return_value=ctx):
            first = [item["key"] for item in rec.generate(days=30)["recommendations"]]
            second = [item["key"] for item in rec.generate(days=30)["recommendations"]]
        self.assertEqual(first, second)
        self.assertTrue(all(":" in key for key in first))

    def test_assumptions_are_published_with_the_output(self):
        """Every threshold that decided what is on this page has to be
        readable from the page itself."""
        with mock.patch.object(rec, "build_context", return_value=context()):
            report = rec.generate(days=30)
        self.assertEqual(report["assumptions"]["wash_cost_per_use"], rec.WASH_COST_PER_USE)
        self.assertEqual(report["assumptions"]["min_observations"], rec.MIN_OBSERVATIONS)

    def test_an_empty_database_produces_nothing_rather_than_filler(self):
        with mock.patch.object(rec, "build_context", return_value=context()):
            report = rec.generate(days=30)
        self.assertEqual(report["generated"], 0)
        self.assertEqual(report["projected_annual_saving"], 0)

    def test_every_recommendation_carries_evidence_and_a_basis(self):
        with mock.patch.object(rec, "build_context", return_value=context(
            products={"DISP-CUP-H12": product(), "REU-MUG-CER12": reusable()},
            by_sku=[sku_row("DISP-CUP-H12", 600)],
            edible_food=[{"building": "Rand Hall", "item": "Scrapings",
                          "count": 20, "cost": 9.0, "grams": 1600.0}],
            misrouted=[{"item": "Straw", "logged_as": "landfill",
                        "should_be": "compost", "count": 18, "grams": 360.0}],
        )):
            report = rec.generate(days=30)
        self.assertTrue(report["recommendations"])
        for item in report["recommendations"]:
            self.assertTrue(item["evidence"], item["key"])
            self.assertTrue(item["basis"], item["key"])
            self.assertIn(item["confidence"], ("high", "medium", "low"))


class CopyTests(unittest.TestCase):
    """These strings are the product. A card reading "Empty the 1 cans"
    reads as broken software, and a reader who notices stops trusting the
    number beside it."""

    def test_plural_agrees_with_its_count(self):
        self.assertEqual(rec._plural(1, "can"), "1 can")
        self.assertEqual(rec._plural(3, "can"), "3 cans")
        self.assertEqual(rec._plural(0, "can"), "0 cans")

    def test_plural_takes_an_irregular_form(self):
        self.assertEqual(rec._plural(2, "analysis", "analyses"), "2 analyses")

    def test_mass_falls_back_to_grams_below_a_kilo(self):
        """"0.0 kg sent down the wrong stream" is true, reads as a bug, and
        tells the reader nothing."""
        self.assertEqual(rec._mass(14.4), "14 g")
        self.assertEqual(rec._mass(999), "999 g")
        self.assertEqual(rec._mass(1500), "1.5 kg")

    def test_catalog_parentheticals_are_dropped_mid_sentence(self):
        self.assertEqual(rec._plain_item("Pizza Crust (uneaten)"), "Pizza Crust")
        self.assertEqual(rec._plain_item("Plate Scrapings"), "Plate Scrapings")


class BacklogFramingTests(unittest.TestCase):
    """The summary has to agree with its own numbers. Claiming a cluster
    while reporting one can per building is a contradiction a reader will
    catch before the dashboard does."""

    def cans_in(self, buildings: list[str]) -> dict:
        return context(fleet=[
            can(can_id=index, can_code=f"C{index}", building_name=name, fill_percent=90.0)
            for index, name in enumerate(buildings, start=1)
        ])

    def test_several_in_one_building_is_described_as_a_missed_stop(self):
        out = rec.service_backlog(self.cans_in(["Rand Hall", "Rand Hall", "Quiet Hall"]))
        self.assertIn("missing a stop", out[0]["summary"])
        self.assertIn("2 cans in Rand Hall", out[0]["action"])

    def test_one_each_across_buildings_is_described_as_a_pacing_problem(self):
        out = rec.service_backlog(self.cans_in(["A Hall", "B Hall", "C Hall"]))
        self.assertIn("pacing problem", out[0]["summary"])
        self.assertNotIn("missing a stop", out[0]["summary"])
        self.assertIn("1 can in", out[0]["action"])

    def test_no_recommendation_ever_says_one_cans(self):
        for buildings in (["A", "A", "B"], ["A", "B", "C"], ["A", "A", "A", "B"]):
            for item in rec.service_backlog(self.cans_in(buildings)):
                for text in (item["summary"], item["action"], item["title"]):
                    self.assertNotIn("1 cans", text)
                    self.assertNotIn("1 units", text)
                    self.assertNotIn("1 buildings", text)


if __name__ == "__main__":
    unittest.main()
