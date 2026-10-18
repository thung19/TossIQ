"""Seeds dish-level food waste at the buildings that actually serve food,
and clears the plate scrapings that ended up somewhere a kitchen is not.

Why this exists separately from seed_campus: that script draws a can's
contents from its building's waste profile, and the compost side of every
profile includes food. So a library, a lab and an admin block all logged
pizza crusts, and Central Library came out as the worst food-waste site on
campus. A library has a coffee cart. It does not have plate scrapings.

What this writes is dish-level: a named menu item per event rather than a
generic "plate scrapings" row. That is the difference between a dashboard
that can say "there is food waste" and one that can say "eighteen per cent
of the halloumi wraps you make come back uneaten, stop making so many".
The advanced vision path can read a tray and name the dish, so this is a
capability the product has rather than one invented for the demo.

!! THE WASTE RATES ARE INVENTED !!
Which dish is over-produced, and by how much, is demo data. The arithmetic
on top of it is real: uneaten servings over servings made, from the
catalog's own production figures.

Run from the repository root, after seed_catalog.py:
    python seed_dining.py

    --clean-nondining   remove edible-food events logged at buildings with
                        no kitchen, which earlier seeds scattered there.
"""

import random
import sys
from datetime import datetime, timedelta

import db

RANDOM_SEED = 20261020

# Buildings with a servery. Everything else gets no prepared food at all:
# a lab, an admin block and a library do not produce plate waste, and
# pretending they do put Central Library top of the food-waste table.
DINING_BUILDINGS = ("VU-RAND", "VU-COMMONS", "VU-SARRATT", "VU-SLC")

# Share of each building's dish waste. Rand is the main servery and the
# building the food-waste initiative targets.
BUILDING_SHARE = {"VU-RAND": 0.46, "VU-COMMONS": 0.24, "VU-SARRATT": 0.18, "VU-SLC": 0.12}

# Uneaten servings per 30 days, per dish, campus-wide. Set against the
# catalog's servings_per_week so the resulting waste RATE is the point:
# the halloumi wrap is the one worth acting on, the salmon bowl is second,
# and everything else is ordinary kitchen loss.
#
# (sku, uneaten servings in 30 days)
DISH_WASTE = [
    ("DISH-WRAP-HALLOUMI", 54),   # ~18% of production: the finding
    ("DISH-BOWL-SALMON", 16),     # ~8%: second, and expensive per serving
    ("DISH-CHILI-BEEF", 22),      # ~4%
    ("DISH-MAC-CHEESE", 30),      # ~3.5%
    ("DISH-SALAD-CAESAR", 20),    # ~3%
    ("DISH-PIZZA-MARG", 40),      # ~3%
    ("DISH-BURRITO-BFAST", 10),   # ~2.6%
    ("DISH-POTATO-ROAST", 35),    # ~3.3%
]

# Meal services. Uneaten food arrives at the tray return just after each
# sitting, not spread evenly through the day.
MEAL_HOURS = ((8, 10), (11, 14), (17, 20))
MEAL_WEIGHTS = (2, 5, 4)

WINDOW_DAYS = 30

_DISH_INSERT = """
INSERT INTO waste_events
    (detected_object, material, category, location, confidence, created_at,
     bin_id, product_id)
VALUES
    (:detected_object, :material, :category, :location, :confidence, :created_at,
     :bin_id, :product_id)
"""


def dining_cans() -> dict[str, list[dict]]:
    """Cans at the serveries, preferring the ones at a tray return.

    Uneaten food arrives where trays are scraped, so weighting those bins
    is what makes the per-can picture match how a dining hall works rather
    than scattering plate waste evenly across the building.
    """
    by_building: dict[str, list[dict]] = {}
    for can in db.list_can_rows():
        prefix = can["can_code"].rsplit("-", 1)[0]
        if prefix in DINING_BUILDINGS:
            by_building.setdefault(prefix, []).append(can)
    return by_building


def pick_can(rng: random.Random, cans: list[dict]) -> dict:
    note = lambda can: (can.get("placement_note") or "").lower()
    trays = [can for can in cans if "tray" in note(can)]
    servery = [can for can in cans if "servery" in note(can)]
    if trays and rng.random() < 0.55:
        return rng.choice(trays)
    if servery and rng.random() < 0.6:
        return rng.choice(servery)
    return rng.choice(cans)


def meal_time(rng: random.Random, now: datetime) -> datetime:
    start, end = rng.choices(MEAL_HOURS, weights=MEAL_WEIGHTS, k=1)[0]
    when = (now - timedelta(days=rng.uniform(0, WINDOW_DAYS))).replace(
        hour=rng.randrange(start, end), minute=rng.randrange(60),
        second=rng.randrange(60), microsecond=0,
    )
    return when - timedelta(days=1) if when > now else when


def seed_dish_waste() -> int:
    rng = random.Random(RANDOM_SEED)
    now = datetime.now()
    products = {p["sku"]: p for p in db.list_products()}
    cans = dining_cans()
    if not cans:
        return 0

    buildings = [b for b in DINING_BUILDINGS if b in cans]
    weights = [BUILDING_SHARE[b] for b in buildings]

    rows = []
    for sku, uneaten in DISH_WASTE:
        product = products.get(sku)
        if not product:
            continue
        for _ in range(uneaten):
            building = rng.choices(buildings, weights=weights, k=1)[0]
            can = pick_can(rng, cans[building])
            rows.append({
                "detected_object": product["product_name"].lower(),
                "material": "organic",
                "category": "compost",
                "location": can["can_code"],
                "confidence": rng.randrange(71, 96),
                "created_at": meal_time(rng, now),
                "bin_id": can["can_id"],
                "product_id": product["product_id"],
            })

    if not rows:
        return 0
    with db.get_connection() as conn, conn.cursor() as cursor:
        cursor.executemany(_DISH_INSERT, rows)
        conn.commit()
    return len(rows)


def clean_nondining_food() -> int:
    """Removes edible-food events logged where there is no kitchen.

    Earlier seeds drew every can's contents from its building's waste
    profile, and every profile has a compost share, so plate waste landed
    in the library, the labs and the admin block. Deleting it is the
    honest fix: those events describe something that does not happen.
    Only synthetic rows are touched, identified as the seeds write them.
    """
    placeholders = ", ".join(f"'{code}'" for code in DINING_BUILDINGS)
    # The events being removed may carry reviews, which hold a foreign key
    # to them. The review is a verdict on an event that should not exist,
    # so it goes with it rather than being orphaned or blocking the delete.
    target = f"""
        SELECT we.event_id
          FROM waste_events we
         WHERE we.image_key IS NULL
           AND we.product_id IN (
                 SELECT product_id FROM products
                  WHERE material_subtype = 'edible food'
               )
           AND NOT EXISTS (
                 SELECT 1 FROM cans c
                  WHERE c.can_id = we.bin_id
                    AND SUBSTR(c.can_code, 1, INSTR(c.can_code, '-', -1) - 1)
                        IN ({placeholders})
               )
    """
    with db.get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(f"DELETE FROM event_reviews WHERE event_id IN ({target})")
        cursor.execute(
            f"""
            DELETE FROM waste_events we
             WHERE we.image_key IS NULL
               AND we.product_id IN (
                     SELECT product_id FROM products
                      WHERE material_subtype = 'edible food'
                   )
               AND NOT EXISTS (
                     SELECT 1 FROM cans c
                      WHERE c.can_id = we.bin_id
                        AND SUBSTR(c.can_code, 1, INSTR(c.can_code, '-', -1) - 1)
                            IN ({placeholders})
                   )
            """
        )
        removed = cursor.rowcount
        conn.commit()
        return removed


def main() -> None:
    clean = "--clean-nondining" in sys.argv

    print("Seeding dish-level food waste at the serveries.")
    print("  WASTE RATES ARE INVENTED -- see module docstring.")

    if clean:
        print(f"  cleaned:         {clean_nondining_food()} food event(s) removed from "
              "buildings with no kitchen")

    print(f"  dish waste:      {seed_dish_waste()} uneaten serving(s)")
    print("Done.")


if __name__ == "__main__":
    main()
