"""Seeds a starting set of initiatives and the projects under them.

Idempotent on initiative name. Targets are set relative to the MEASURED
current value (cut this by 60%, lift that to 75%), so they stay sensible
whatever the database happens to hold when this runs. A goal hardcoded to
"reduce to 400 items" against a database with 300 in it would show as
achieved before anybody did anything.

!! SEEDED BASELINES ARE BACKDATED, NOT MEASURED !!
A baseline is what the number was BEFORE the work started, which needs
months of history this demo database does not have -- its disposals span
about two weeks. So each seeded initiative's baseline is derived from the
current measurement times a plausible "we were this much worse when we set
the goal" factor, and BASELINE_CAPTURED_AT is backdated to match. That is
what makes the progress bars show anything at all.

Goals created through the API measure their baseline from live data at the
moment of creation, which is the honest path and the one the product
actually uses. This file is the only place a baseline is invented.

Run from the repository root, after schema/apply.py and the other seeds:
    python seed_initiatives.py
"""

import sys
from datetime import date, timedelta

import db
import initiatives

# (name, description, owner, metric, direction, scope, target_rule,
#  baseline_factor, days_out, days_since_set)
#
# target_rule is (kind, value): "factor" multiplies the current measurement,
# "absolute" sets the target outright. baseline_factor is how much worse
# things were when the goal was set -- above 1 for a reduction goal, below 1
# for one being lifted.
INITIATIVES = [
    (
        "Cut bottled water across campus",
        "Bottled water is the single largest avoidable SKU in the catalog. "
        "Displace it with refill infrastructure rather than switching brands.",
        "sustainability@vanderbilt.edu",
        "items", "reduce",
        {"scope_object": "plastic water bottle"},
        ("factor", 0.4), 1.30, 180, 45,
    ),
    (
        "Reach 75% diversion campus-wide",
        "Share of disposals going to recycling or compost rather than landfill. "
        "The headline sustainability commitment for the academic year.",
        "sustainability@vanderbilt.edu",
        "diversion_rate", "increase",
        {},
        ("absolute", 75.0), 0.88, 270, 70,
    ),
    (
        "Halve landfill volume at Rand Hall",
        "Rand is the busiest dining building and sets the pattern the other "
        "servery sites copy. Prove it there first.",
        "dining-ops@vanderbilt.edu",
        "landfill_items", "reduce",
        {"scope_building": "VU-RAND"},
        ("factor", 0.5), 1.55, 150, 60,
    ),
    (
        "Cut $2.5k from annual disposal cost",
        "Catalog loss-on-discard for everything logged. Tracks the money side "
        "of the same work the other initiatives do.",
        "facilities-ops@vanderbilt.edu",
        "cost", "reduce",
        {},
        ("factor", 0.7), 1.18, 365, 90,
    ),
    (
        "Eliminate hazardous items from general bins",
        "Vapes, batteries and sharps in a general bin are the one failure mode "
        "that can injure a handler. Target is zero, and will not be met, but "
        "the trend is the point.",
        "ehs@vanderbilt.edu",
        "hazard_events", "reduce",
        {},
        ("absolute", 0.0), 1.05, 365, 30,
    ),
    (
        "Get wrong-bin sorting under 3%",
        "Items put in a bin the catalog says is the wrong one. A contaminated "
        "load gets rejected whole at the sorting facility, so the rate matters "
        "far more than the tonnage.",
        "sustainability@vanderbilt.edu",
        "contamination_rate", "reduce",
        {},
        ("absolute", 3.0), 0.92, 200, 40,
    ),
    (
        # Scoped to the edible-food metric, not to "cost of everything in the
        # compost bin". The first version measured the latter and produced a
        # goal to cut $3 to $1, because peels and spent grounds are priced at
        # zero -- so the slice it measured was almost empty and the target was
        # noise with a percentage sign on it.
        "Cut edible food waste campus-wide",
        "Food that was served and not eaten, at catalog value. Peels, cores and "
        "spent grounds are excluded: the product they came from was used.",
        "dining-ops@vanderbilt.edu",
        "food_waste_cost", "reduce",
        {},
        ("factor", 0.55), 1.6, 120, 55,
    ),
]

# (initiative name, project name, description, owner, status, impact, note,
#  recommendation key, due in days)
PROJECTS = [
    ("Cut bottled water across campus",
     "Install refill stations in Rand, Commons and the Library",
     "Three high-traffic buildings first. Costed from the recommendation card.",
     "facilities-ops@vanderbilt.edu", "in_progress", 600.0,
     "Displaces roughly 600 bottles a year across the three sites",
     "infrastructure:BEV-WTR-0591-VU", 90),
    ("Cut bottled water across campus",
     "Stop stocking own-brand bottled water at the Library cafe",
     "The cheapest SKU is also the highest volume. Remove it where a tap is "
     "within sight of the till.",
     "dining-ops@vanderbilt.edu", "proposed", 200.0,
     "Removes the highest-volume variant from one site", None, 60),
    ("Cut bottled water across campus",
     "Signage at every refill point",
     "Wayfinding so the station is findable from the queue, not only from the corridor.",
     "sustainability@vanderbilt.edu", "proposed", None, None, None, 120),

    ("Reach 75% diversion campus-wide",
     "Re-label landfill apertures where compostables are going in",
     "Four misrouting patterns are live on the quality tab; the apertures are "
     "the common factor.",
     "facilities-ops@vanderbilt.edu", "in_progress", None,
     "Should move most of the compostable straws and clamshells", None, 75),
    ("Reach 75% diversion campus-wide",
     "Switch PP straws to the compostable paper line",
     "Same supplier, same order, and it goes in the compost bin.",
     "dining-ops@vanderbilt.edu", "done", None, None,
     "material:DISP-STR-PP8", -20),

    ("Halve landfill volume at Rand Hall",
     "Move the quiet Rand bins onto the traffic filling VU-RAND-02",
     "VU-RAND-02 is at 96% while VU-RAND-01 sits at 1% in the same building.",
     "facilities-ops@vanderbilt.edu", "in_progress", None, None,
     "rebalance:Rand Hall", 30),
    ("Halve landfill volume at Rand Hall",
     "Add a compost bin at the Rand servery exit",
     "Most of what leaves the servery is compostable and there is nowhere to put it.",
     "dining-ops@vanderbilt.edu", "blocked", None,
     "Blocked on the compost hauler contract renewal", None, 100),

    ("Cut $2.5k from annual disposal cost",
     "Review portion sizes at Central Library cafe",
     "Plate scrapings are the largest single edible-food line.",
     "dining-ops@vanderbilt.edu", "proposed", 148.0,
     "Projected from the recommendation card",
     "portions:Central Library", 90),

    ("Eliminate hazardous items from general bins",
     "Battery and vape collection tubes at Branscomb and Highland",
     "Both residences show recurring vape disposals across multiple cans.",
     "ehs@vanderbilt.edu", "in_progress", None,
     "Gives the items somewhere correct to go, which signage alone does not",
     None, 45),
    ("Eliminate hazardous items from general bins",
     "Lab solvent disposal briefing for Stevenson",
     "Five solvent disposals in thirty days, all in one building.",
     "ehs@vanderbilt.edu", "proposed", None, None, None, 60),

    ("Get wrong-bin sorting under 3%",
     "Retrain the sorter on paper cup sleeves",
     "The biggest single wrong-bin contributor: going in compost, belongs in recycling.",
     "sustainability@vanderbilt.edu", "proposed", None, None, None, 80),

    ("Cut edible food waste campus-wide",
     "Trial smaller default portions at the Commons hot line",
     "Two-week trial, re-measure after.",
     "dining-ops@vanderbilt.edu", "proposed", None, None, None, 45),
]


def resolve_scope(scope: dict) -> dict:
    """Turns the seed's friendly scope into stored columns.

    Buildings are named by code here and stored by id, because a code is
    readable in this file and an id is the thing the schema references.
    """
    resolved = {}
    building_code = scope.get("scope_building")
    if building_code:
        match = next(
            (b for b in db.list_buildings() if b["building_code"] == building_code), None
        )
        if match:
            resolved["scope_building_id"] = match["building_id"]
    for key in ("scope_category", "scope_material", "scope_object", "scope_supplier"):
        if scope.get(key):
            resolved[key] = scope[key]
    return resolved


def apply_target(rule: tuple, current: float) -> float:
    kind, value = rule
    if kind == "absolute":
        return float(value)
    return round(current * value, 3)


def seed_initiatives() -> tuple[int, int]:
    existing = {row["name"] for row in db.list_initiatives()}
    created = 0
    skipped = 0

    for (name, description, owner, metric, direction, scope, target_rule,
         baseline_factor, days_out, days_since_set) in INITIATIVES:
        if name in existing:
            skipped += 1
            continue

        columns = {
            "name": name,
            "description": description,
            "owner": owner,
            "metric": metric,
            "direction": direction,
            "baseline_window_days": 30,
            "status": "active",
            "target_date": date.today() + timedelta(days=days_out),
            **resolve_scope(scope),
        }

        # The current measurement is real; the baseline is derived from it.
        # See the module docstring: a true baseline needs history this demo
        # database does not have.
        current = initiatives.measure({**columns, "baseline_window_days": 30}) or 0.0
        columns["baseline_value"] = round(current * baseline_factor, 3)
        columns["target_value"] = apply_target(target_rule, current)

        initiative_id = db.insert_initiative(**columns)
        # Backdate the capture so the baseline reads as what it is: a figure
        # from when the goal was set, not from this morning.
        db.backdate_initiative_baseline(initiative_id, days_since_set)
        created += 1

    return created, skipped


def seed_projects() -> tuple[int, int]:
    by_name = {row["name"]: row["initiative_id"] for row in db.list_initiatives()}
    existing = {(row["initiative_id"], row["name"]) for row in db.list_projects()}
    created = 0
    skipped = 0

    for (initiative_name, name, description, owner, status, impact, note,
         recommendation_key, days_out) in PROJECTS:
        initiative_id = by_name.get(initiative_name)
        if initiative_id is None:
            continue
        if (initiative_id, name) in existing:
            skipped += 1
            continue

        columns = {
            "initiative_id": initiative_id,
            "name": name,
            "description": description,
            "owner": owner,
            "status": status,
            "expected_impact": impact,
            "expected_impact_note": note,
            "source_recommendation_key": recommendation_key,
            "due_date": date.today() + timedelta(days=days_out),
        }
        if status in ("in_progress", "done", "blocked"):
            columns["started_at"] = None
        if status == "done":
            columns["completed_at"] = None

        db.insert_project(**{k: v for k, v in columns.items() if v is not None})
        created += 1

    return created, skipped


def main() -> None:
    if "--help" in sys.argv:
        print(__doc__)
        return

    print("Seeding initiatives and projects.")
    print("  SEEDED BASELINES ARE BACKDATED, NOT MEASURED -- see module docstring.")

    created, skipped = seed_initiatives()
    print(f"  initiatives:     {created} new, {skipped} already present")

    created, skipped = seed_projects()
    print(f"  projects:        {created} new, {skipped} already present")
    print("Done.")


if __name__ == "__main__":
    main()
