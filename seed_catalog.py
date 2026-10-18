"""Seeds the organization supplies catalog and the review trail analytics
needs, then attributes existing disposal events to catalog products.

Idempotent and re-runnable, like seed_campus.py: products are matched on their
natural SKU and inserted only when absent, and the attribution and review
passes skip rows that already carry the thing they would write.

Three honesty rules are encoded in the data here, not just in the UI:

  * UNIT_WEIGHT_GRAMS is a CATALOG REFERENCE MASS -- what one of these weighs
    empty, from the supplier's spec. No can has a weight sensor (CLAUDE.md
    records that as a hard hardware constraint), so every mass this product
    reports is items x reference mass. It is an estimate and the API says so.

  * UNIT_COST is the loss incurred by throwing the item away, which is NOT
    always the purchase price. A banana peel costs 0.00: the banana was
    eaten, and billing the organization for its peel would invent waste that
    did not happen. A whole discarded banana costs the full 0.32. Plate
    scrapings and pizza crusts sit in between -- edible food that was paid
    for and not eaten -- and carry a real cost. An item with no catalog match
    carries NULL, which the API reports as unknown rather than as zero.

  * Several products share one DETECTED_AS label, because the vision label
    genuinely cannot tell a 500 mL Dasani from a 1 L Smartwater. Which
    variant a seeded event is attributed to is demo data, and every row this
    script writes is stamped MATCH_METHOD = 'seeded' so the analytics page
    can separate it from a live token or image-embedding match.

Run from the repository root, after schema/apply.py:
    python seed_catalog.py

Flags:
    --reseed-reviews        add review rows for events that have none, after
                            the event population has grown.
    --normalize-confidence  rescale CONFIDENCE values written on a 0-1 scale
                            to the 0-100 the column is documented to hold.
                            camera_service.py used to persist the detector's
                            raw score while api.py wrote percentages into the
                            same column, so averages over it mixed units.
                            camera_service.py now scales on write; this
                            repairs the rows from before it did.
"""

import random
import sys
from datetime import datetime, timedelta

import db

RANDOM_SEED = 20261018

# Share of events a human has actually looked at. Deliberately a minority:
# nobody reviews every disposal, and an accuracy figure quoted over 100% of
# events would be the giveaway that the review trail is fictional.
REVIEW_COVERAGE = 0.14

# What fraction of reviewed events the reviewer agreed with, before confidence
# weighting. The seeded errors are concentrated in low-confidence events (see
# review_verdict), so the calibration chart shows the relationship a working
# classifier has rather than uniform noise.
BASE_AGREEMENT = 0.90


# ---------------------------------------------------------------------------
# The catalog
# ---------------------------------------------------------------------------
# Each row is CATALOG_FIELDS in order. Positional rather than a dict purely
# for readability at 47 rows; CATALOG_FIELDS is what anything reading them
# should zip against, rather than counting tuple positions by hand.
#
# Costs are plausible campus-supply prices and masses are plausible empty
# weights; both are demo data, not a procurement record.
CATALOG_FIELDS = (
    "sku", "product_name", "brand", "variant_label", "supplier", "detected_as",
    "material", "material_subtype", "unit_cost", "unit_weight_grams",
    "disposal_category", "recyclable", "reusable", "case_pack_qty", "case_cost",
)

# Reusable programmes and the disposables they replace. Declared here rather
# than inferred from the catalog, because "what replaces what" is a
# procurement judgement: a 12 oz paper hot cup and a 20 oz PET cold cup share
# the vision label "cup" and substitute for each other in no kitchen at all.
#
# EXPECTED_USES is the service life one unit is rated for, and it is what
# turns a reusable recommendation into arithmetic. A disposable is 1.
#
# (sku, substitute_sku, kind, substitute_note)
#
# `kind` decides which recommendation this becomes, and they are not
# interchangeable. "material" changes a purchase order and is realistic
# anywhere. "reuse" needs service where the item comes back, which a
# grab-and-go counter is not. "infrastructure" removes the need to buy the
# item at all and is where the large wins are.
SUBSTITUTIONS = [
    # Infrastructure: the biggest avoidable SKU on campus by a wide margin.
    # The answer to bottled water is a tap, not handing every student a
    # flask and hoping.
    ("BEV-WTR-0500-DAS", "REU-BTL-STL", "infrastructure",
     "Refill stations remove the purchase entirely. Branded premium water; "
     "the most expensive of the three per unit."),
    ("BEV-WTR-1000-SMW", "REU-BTL-STL", "infrastructure",
     "Refill stations remove the purchase entirely. Premium large-format water."),
    ("BEV-WTR-0591-VU", "REU-BTL-STL", "infrastructure",
     "Refill stations remove the purchase entirely. Own-brand water and the "
     "highest-volume of the three."),

    # Material: a different disposable, same service. Changes the order and
    # nothing about how the counter operates.
    ("DISP-STR-PP8", "DISP-STR-PPR", "material",
     "Paper straw is compostable and stocked by the same supplier."),
    ("DISP-CLM-PET9", "DISP-CLM-FIB6", "material",
     "Fibre clamshell is compostable and lighter; the PET one is recyclable "
     "only when clean, which a food container rarely is."),
    ("DISP-CUP-EPS08", "DISP-CUP-H12", "material",
     "Foam is landfill-only. Note the paper replacement is four times the mass, "
     "so this is a policy and recyclability change, not a carbon saving."),

    # Reuse: only where service is dine-in and the item comes back on a tray.
    ("DISP-CUT-PPF", "REU-CUT-STL", "reuse",
     "Stainless flatware for dine-in tray service only; keep disposables for takeaway."),
    ("DISP-CUT-PPS", "REU-CUT-STL", "reuse",
     "Stainless flatware for dine-in tray service only; keep disposables for takeaway."),
    ("DISP-CUT-PPK", "REU-CUT-STL", "reuse",
     "Stainless flatware for dine-in tray service only; keep disposables for takeaway."),
    ("DISP-CUP-H12", "REU-MUG-CER12", "reuse",
     "Ceramic mugs for seated cafe service only. Not viable at a grab-and-go "
     "counter, where nothing comes back."),
    ("DISP-CUP-H16", "REU-MUG-CER12", "reuse",
     "Ceramic mugs for seated cafe service only. Not viable at a grab-and-go "
     "counter, where nothing comes back."),
]

# The reusable programmes themselves. They are catalog products like any
# other so their cost per use is auditable: price divided by EXPECTED_USES,
# plus the washing cost recommendations.py applies.
REUSABLE_PROGRAMMES = [
    # (sku, name, supplier, material, unit_cost, grams, stream, expected_uses)
    ("REU-MUG-CER12", "Ceramic Mug 12 oz (reusable)", "Imperial Dade", "ceramic",
     4.20, 310.0, "landfill", 500),
    ("REU-CUT-STL", "Stainless Flatware, 3-piece (reusable)", "Imperial Dade", "metal",
     3.80, 125.0, "recycling", 800),
    ("REU-BTL-STL", "Insulated Steel Bottle 600 mL (reusable)", "Chef Works", "metal",
     11.50, 290.0, "recycling", 1200),
]


CATALOG = [
    # --- Bottled drinks: three variants behind one vision label -------------
    ("BEV-WTR-0500-DAS", "Dasani Purified Water 500 mL", "Dasani", "500 mL PET bottle",
     "Coca-Cola Consolidated", "plastic water bottle", "plastic", "PET", 1.45, 10.5,
     "recycling", 1, 0, 24, 30.60),
    ("BEV-WTR-1000-SMW", "Smartwater 1 L", "Smartwater", "1 L PET bottle",
     "Coca-Cola Consolidated", "plastic water bottle", "plastic", "PET", 2.75, 28.0,
     "recycling", 1, 0, 12, 29.40),
    ("BEV-WTR-0591-VU", "Vanderbilt Blend Spring Water 591 mL", "Vanderbilt Dining",
     "591 mL PET bottle", "Campus Dining", "plastic water bottle", "plastic", "PET",
     1.25, 12.0, "recycling", 1, 0, 24, 26.40),
    ("BEV-SOD-0355-COKE", "Coca-Cola Classic 12 oz can", "Coca-Cola", "355 mL aluminium can",
     "Coca-Cola Consolidated", "aluminum can", "metal", "aluminium", 1.10, 14.9,
     "recycling", 1, 0, 24, 21.60),
    ("BEV-SPK-0355-LAC", "LaCroix Sparkling Water 12 oz", "LaCroix", "355 mL aluminium can",
     "US Foods", "aluminum can", "metal", "aluminium", 1.35, 14.2,
     "recycling", 1, 0, 24, 25.90),
    ("BEV-NRG-0250-RB", "Red Bull Energy Drink 8.4 oz", "Red Bull", "250 mL aluminium can",
     "US Foods", "aluminum can", "metal", "aluminium", 3.25, 12.5,
     "recycling", 1, 0, 24, 62.40),
    ("BEV-TEA-0473-SNP", "Snapple Lemon Tea 16 oz", "Snapple", "473 mL glass bottle",
     "US Foods", "glass bottle", "glass", "soda-lime", 2.50, 215.0,
     "recycling", 1, 0, 12, 26.40),
    ("BEV-KOM-0473-GT", "GT's Kombucha 16 oz", "GT's", "473 mL glass bottle",
     "Whole Foods Wholesale", "glass bottle", "glass", "soda-lime", 3.95, 230.0,
     "recycling", 1, 0, 12, 43.80),

    # --- Hot and cold drinkware --------------------------------------------
    ("DISP-CUP-H12", "Paper Hot Cup 12 oz", "Imperial Dade", "12 oz double-wall paper",
     "Imperial Dade", "cup", "paper", "poly-lined paperboard", 0.11, 11.0,
     "landfill", 0, 0, 1000, 94.00),
    ("DISP-CUP-H16", "Paper Hot Cup 16 oz", "Imperial Dade", "16 oz double-wall paper",
     "Imperial Dade", "cup", "paper", "poly-lined paperboard", 0.13, 13.5,
     "landfill", 0, 0, 1000, 112.00),
    ("DISP-CUP-C20", "PET Cold Cup 20 oz", "Imperial Dade", "20 oz clear PET",
     "Imperial Dade", "cup", "plastic", "PET", 0.16, 15.0,
     "recycling", 1, 0, 1000, 139.00),
    ("DISP-CUP-EPS08", "Foam Cup 8 oz (legacy)", "Dart", "8 oz expanded polystyrene",
     "Imperial Dade", "styrofoam cup", "plastic", "EPS", 0.06, 2.6,
     "landfill", 0, 0, 1000, 48.00),
    ("DISP-LID-D20", "Dome Lid 12-20 oz", "Dart", "PS dome lid",
     "Imperial Dade", "coffee lid", "plastic", "PS", 0.040, 3.2,
     "landfill", 0, 0, 1000, 34.00),
    ("DISP-LID-F12", "Flat Sip Lid 12 oz", "Dart", "PS flat lid",
     "Imperial Dade", "coffee lid", "plastic", "PS", 0.035, 2.8,
     "landfill", 0, 0, 1000, 29.50),
    ("DISP-SLV-KRF", "Kraft Cup Sleeve", "Imperial Dade", "corrugated kraft sleeve",
     "Imperial Dade", "cardboard sleeve", "paper", "corrugated kraft", 0.025, 4.5,
     "recycling", 1, 0, 1000, 22.00),
    ("DISP-SLV-PCS", "Paper Cup Sleeve (unbranded)", "Imperial Dade", "plain kraft sleeve",
     "Imperial Dade", "paper cup sleeve", "paper", "corrugated kraft", 0.022, 4.2,
     "recycling", 1, 0, 1000, 19.50),

    # --- Servingware --------------------------------------------------------
    ("DISP-CLM-PET9", "Hinged Clamshell 9 in", "Imperial Dade", "9 in clear PET hinged",
     "Imperial Dade", "plastic clamshell", "plastic", "PET", 0.28, 32.0,
     "recycling", 1, 0, 200, 54.00),
    ("DISP-CLM-FIB6", "Compostable Fibre Clamshell 6 in", "World Centric",
     "6 in moulded fibre", "Imperial Dade", "plastic clamshell", "fibre", "bagasse",
     0.34, 21.0, "compost", 0, 0, 400, 132.00),
    ("DISP-TRY-P50", "Paper Food Tray #50", "Imperial Dade", "#50 kraft boat",
     "Imperial Dade", "paper food boat", "paper", "kraft board", 0.050, 8.0,
     "compost", 0, 0, 1000, 46.00),
    ("DISP-CNT-PP32", "Deli Container 32 oz", "Imperial Dade", "32 oz PP round",
     "Imperial Dade", "plastic container", "plastic", "PP", 0.42, 28.0,
     "recycling", 1, 1, 240, 96.00),
    ("DISP-CNT-PET16", "Deli Container 16 oz", "Imperial Dade", "16 oz PET round",
     "Imperial Dade", "plastic container", "plastic", "PET", 0.26, 18.0,
     "recycling", 1, 1, 240, 59.00),

    # --- Cutlery ------------------------------------------------------------
    ("DISP-CUT-PPF", "Heavy Fork", "Dixie", "heavyweight PP fork",
     "Imperial Dade", "plastic cutlery", "plastic", "PP", 0.030, 4.4,
     "landfill", 0, 0, 1000, 26.00),
    ("DISP-CUT-PPS", "Heavy Spoon", "Dixie", "heavyweight PP spoon",
     "Imperial Dade", "plastic cutlery", "plastic", "PP", 0.030, 4.1,
     "landfill", 0, 0, 1000, 26.00),
    ("DISP-CUT-PPK", "Heavy Knife", "Dixie", "heavyweight PP knife",
     "Imperial Dade", "plastic cutlery", "plastic", "PP", 0.030, 4.3,
     "landfill", 0, 0, 1000, 26.00),
    ("DISP-CUT-CPF", "Compostable Fork", "World Centric", "CPLA compostable fork",
     "Imperial Dade", "compostable fork", "bioplastic", "CPLA", 0.060, 5.1,
     "compost", 0, 0, 1000, 54.00),
    ("DISP-STR-PP8", "Drinking Straw 7.75 in", "Dart", "PP wrapped straw",
     "Imperial Dade", "plastic straw", "plastic", "PP", 0.012, 0.50,
     "landfill", 0, 0, 2000, 22.00),
    ("DISP-STR-PPR", "Paper Straw 7.75 in", "Aardvark", "paper wrapped straw",
     "Imperial Dade", "plastic straw", "paper", "kraft paper", 0.025, 0.80,
     "compost", 0, 0, 2000, 46.00),
    ("DISP-NAP-1PLY", "Dispenser Napkin 1-ply", "Tork", "1-ply interfold",
     "Imperial Dade", "napkin", "paper", "tissue", 0.008, 1.9,
     "compost", 0, 0, 6000, 44.00),

    # --- Snacks and packaging ----------------------------------------------
    ("SNK-CHP-SUN15", "Sun Chips Harvest Cheddar 1.5 oz", "Sun Chips", "1.5 oz bag",
     "Frito-Lay", "chip bag", "plastic", "metallised BOPP", 1.75, 5.5,
     "landfill", 0, 0, 64, 78.00),
    ("SNK-CHP-LAY10", "Lay's Classic 1 oz", "Lay's", "1 oz bag",
     "Frito-Lay", "chip bag", "plastic", "metallised BOPP", 1.50, 4.8,
     "landfill", 0, 0, 104, 109.00),
    ("SNK-BAR-CLIF", "Clif Bar Chocolate Chip", "Clif", "68 g bar wrapper",
     "US Foods", "food wrapper", "plastic", "multilayer film", 2.25, 3.2,
     "landfill", 0, 0, 12, 21.60),
    ("SNK-CND-SNK", "Snickers Bar", "Snickers", "52 g bar wrapper",
     "US Foods", "candy wrapper", "plastic", "multilayer film", 1.65, 2.8,
     "landfill", 0, 0, 48, 62.40),

    # --- Office and facilities ---------------------------------------------
    ("OFF-PPR-LTR20", "Copy Paper 8.5x11 20 lb (sheet)", "Hammermill", "letter sheet",
     "Office Depot Business", "printer paper", "paper", "uncoated white", 0.012, 4.5,
     "recycling", 1, 0, 5000, 54.00),
    ("OFF-NBK-CR", "Notebook Sheet College-Ruled", "Mead", "college-ruled sheet",
     "Office Depot Business", "notebook page", "paper", "uncoated white", 0.015, 3.3,
     "recycling", 1, 0, 1000, 14.50),
    ("OFF-PPR-GEN", "Loose Paper (unidentified stock)", None, "mixed office paper",
     "Office Depot Business", "paper", "paper", "mixed grade", 0.012, 4.2,
     "recycling", 1, 0, None, None),
    ("SHP-BOX-S", "Corrugated Shipping Box, small", "Uline", "8x6x4 in RSC",
     "Uline", "cardboard", "paper", "corrugated", 0.85, 180.0,
     "recycling", 1, 1, 25, 21.25),
    ("SAF-GLV-NIT", "Nitrile Glove (each)", "Microflex", "powder-free nitrile",
     "Fisher Scientific", "disposable glove", "plastic", "nitrile", 0.045, 3.8,
     "landfill", 0, 0, 1000, 45.00),
    ("FDS-CAN-10", "#10 Steel Food Can", None, "#10 tinplate can",
     "US Foods", "metal can", "metal", "tinplate steel", 4.20, 350.0,
     "recycling", 1, 0, 6, 25.20),
    ("UNI-APR-CTN", "Cotton Service Apron", "Chef Works", "cotton bib apron",
     "Chef Works", "textile", "textile", "cotton", 12.00, 240.0,
     "landfill", 0, 1, 12, 144.00),

    # --- Food: consumed residue vs. food actually wasted --------------------
    # Residue carries 0.00 -- the product was eaten, and charging the
    # organization for the peel would invent a loss that did not occur.
    ("PRD-FRT-BAN-PEEL", "Banana Peel (consumed residue)", None, "post-consumption residue",
     "Campus Dining", "banana peel", "organic", "fruit residue", 0.00, 45.0,
     "compost", 0, 0, None, None),
    ("PRD-FRT-APL-CORE", "Apple Core (consumed residue)", None, "post-consumption residue",
     "Campus Dining", "apple core", "organic", "fruit residue", 0.00, 28.0,
     "compost", 0, 0, None, None),
    ("PRD-COF-GRND", "Spent Coffee Grounds", None, "brewed residue",
     "Campus Dining", "coffee grounds", "organic", "spent grounds", 0.00, 20.0,
     "compost", 0, 0, None, None),
    ("GRD-VEG-TRIM", "Landscaping Trimmings", None, "grounds-crew green waste",
     "Campus Grounds", "vegetation", "organic", "green waste", 0.00, 150.0,
     "compost", 0, 0, None, None),
    # Edible food that was paid for and not eaten: a real, recoverable loss.
    ("PRD-PZA-CRUST", "Pizza Crust (uneaten)", None, "uneaten portion",
     "Campus Dining", "pizza crust", "organic", "edible food", 0.30, 45.0,
     "compost", 0, 0, None, None),
    # Priced as a PORTION of food, which is what it is. The first version
    # had this at $0.45 and 85 g -- a plate of uneaten servery food costed
    # at forty-five cents -- and since it is the largest edible-food line by
    # a distance, it made campus food waste read as $40 a month and any goal
    # built on it look pointless.
    ("PRD-FD-SCRAP", "Plate Scrapings (uneaten)", None, "uneaten portion",
     "Campus Dining", "food scraps", "organic", "edible food", 2.75, 190.0,
     "compost", 0, 0, None, None),
    ("PRD-FRT-BAN", "Banana, whole (discarded)", None, "whole unconsumed unit",
     "Campus Dining", "banana", "organic", "edible food", 0.32, 118.0,
     "compost", 0, 0, None, None),
    ("PRD-FRT-APL", "Apple, whole (discarded)", None, "whole unconsumed unit",
     "Campus Dining", "apple", "organic", "edible food", 0.55, 182.0,
     "compost", 0, 0, None, None),
]

def catalog_rows() -> list[dict]:
    """CATALOG as dicts keyed by CATALOG_FIELDS."""
    return [dict(zip(CATALOG_FIELDS, row)) for row in CATALOG]

# Vision labels that deliberately resolve to no catalog product. "mixed trash"
# names a bag of unidentifiable material and "bottle" / "water bottle" / "cup"
# are the generic fallbacks the detector emits when it cannot read a brand.
# They are listed here so the analytics page can distinguish "we have no
# catalog entry for this" from "we forgot to seed one", and so a reviewer can
# see the unmatched share is a known quantity rather than an oversight.
DELIBERATELY_UNMATCHED = {"mixed trash"}

# Generic labels that map onto the cheapest plausible variant: the detector
# saw a bottle but could not read which, so the catalog's own entry-level
# product is the conservative attribution.
GENERIC_LABEL_FALLBACK = {
    "bottle": "BEV-WTR-0591-VU",
    "water bottle": "BEV-WTR-0591-VU",
    "Sun Chips bag": "SNK-CHP-SUN15",
}

# Relative likelihood of each variant behind a shared vision label. Written
# out rather than uniform so the variant breakdown looks like a campus that
# buys more of the cheap bottle than the premium one.
VARIANT_WEIGHTS = {
    "BEV-WTR-0591-VU": 5, "BEV-WTR-0500-DAS": 3, "BEV-WTR-1000-SMW": 1,
    "BEV-SOD-0355-COKE": 5, "BEV-SPK-0355-LAC": 3, "BEV-NRG-0250-RB": 2,
    "BEV-TEA-0473-SNP": 3, "BEV-KOM-0473-GT": 1,
    "DISP-CUP-H12": 4, "DISP-CUP-H16": 3, "DISP-CUP-C20": 3,
    "DISP-LID-D20": 3, "DISP-LID-F12": 2,
    "DISP-CLM-PET9": 3, "DISP-CLM-FIB6": 2,
    "DISP-CNT-PP32": 2, "DISP-CNT-PET16": 3,
    "DISP-CUT-PPF": 4, "DISP-CUT-PPS": 3, "DISP-CUT-PPK": 2,
    "DISP-STR-PP8": 4, "DISP-STR-PPR": 2,
    "SNK-CHP-SUN15": 2, "SNK-CHP-LAY10": 3,
}

# Pairs the classifier genuinely confuses, as (seen_as, actually_was). Seeded
# corrections are drawn from here rather than at random, so the confusion
# matrix shows plausible failure modes -- a compostable fork read as plastic
# cutlery, a fibre clamshell read as a PET one -- instead of noise.
CONFUSABLE = [
    ("compostable fork", "plastic cutlery", "landfill", "compost"),
    ("plastic cutlery", "compostable fork", "compost", "landfill"),
    ("cup", "styrofoam cup", "landfill", "landfill"),
    ("styrofoam cup", "cup", "landfill", "landfill"),
    ("plastic clamshell", "paper food boat", "compost", "compost"),
    ("paper food boat", "plastic clamshell", "recycling", "recycling"),
    ("napkin", "paper", "recycling", "compost"),
    ("paper", "napkin", "compost", "recycling"),
    ("plastic container", "plastic clamshell", "recycling", "recycling"),
    ("glass bottle", "plastic water bottle", "recycling", "recycling"),
    ("food scraps", "pizza crust", "compost", "compost"),
    ("chip bag", "candy wrapper", "landfill", "landfill"),
]

REVIEWERS = [
    "m.okafor@vanderbilt.edu", "s.reyes@vanderbilt.edu",
    "j.lindqvist@vanderbilt.edu", "facilities-audit@vanderbilt.edu",
]


# ---------------------------------------------------------------------------
# Seeding passes
# ---------------------------------------------------------------------------

_PRODUCT_COLUMNS = (
    "product_name", "brand", "variant_label", "supplier", "detected_as",
    "material", "material_subtype", "unit_cost", "unit_weight_grams",
    "disposal_category", "recyclable", "reusable", "case_pack_qty",
    "case_cost", "active",
)


def seed_products() -> tuple[int, int]:
    """Inserts every catalog row that is not already present, keyed on SKU.

    Returns (inserted, already_present). An existing row is left exactly as it
    is -- someone may have corrected a price by hand, and a seed that
    overwrote that would be worse than useless.
    """
    inserted = 0
    present = 0
    for row in catalog_rows():
        sku = row.pop("sku")
        if db.product_id_for_sku(sku) is not None:
            present += 1
            continue
        db.upsert_product_by_sku(sku, active=1, **row)
        inserted += 1
    return inserted, present



# Catalog rows that predate schema 002 and so carry none of the detail the
# analytics page needs. They are completed rather than replaced: the row, its
# product_id and any events already attributed to it all stay put, and only
# the columns that are NULL get filled. Keyed on SKU, like everything else.
LEGACY_PRODUCT_DETAIL = {
    "BOT-001": {
        "brand": "Vanderbilt Dining",
        "variant_label": "unspecified bottle (legacy catalog row)",
        "detected_as": "plastic water bottle",
        "material_subtype": "PET",
        "unit_weight_grams": 12.0,
        "disposal_category": "recycling",
        "recyclable": 1,
        "reusable": 0,
        "active": 1,
    },
}


def complete_legacy_products() -> int:
    """Fills the post-002 columns on catalog rows created before they existed.

    Only NULL columns are written, so a value someone has since set by hand
    survives. Without this the one pre-existing product -- which already has
    events attributed to it -- contributes no mass, no stream and no variant
    name, and shows up on the analytics page as an unexplained hole rather
    than as a bottle.
    """
    filled = 0
    for sku, columns in LEGACY_PRODUCT_DETAIL.items():
        if db.product_id_for_sku(sku) is None:
            continue
        filled += db.fill_null_product_columns(sku, columns)
    return filled


def seed_reusable_programmes() -> int:
    """Adds the reusable products the switch recommendations point at.

    They are ordinary catalog rows, not a special case, so the cost-per-use
    comparison the recommendation shows is a comparison between two catalog
    products a reviewer can check. DETECTED_AS is left NULL: a ceramic mug is
    not something the bins should ever log, and giving it a vision label
    would make it eligible for disposal attribution.
    """
    inserted = 0
    for sku, name, supplier, material, cost, grams, stream, uses in REUSABLE_PROGRAMMES:
        if db.product_id_for_sku(sku) is not None:
            continue
        db.upsert_product_by_sku(
            sku,
            product_name=name,
            supplier=supplier,
            material=material,
            material_subtype="durable goods",
            unit_cost=cost,
            unit_weight_grams=grams,
            disposal_category=stream,
            recyclable=1 if stream == "recycling" else 0,
            reusable=1,
            expected_uses=uses,
            active=1,
        )
        inserted += 1
    return inserted


def apply_substitutions() -> int:
    """Records which product replaces which, for rows that do not say yet."""
    written = 0
    for sku, substitute_sku, kind, note in SUBSTITUTIONS:
        if db.product_id_for_sku(sku) is None:
            continue
        written += db.fill_null_product_columns(sku, {
            "substitute_sku": substitute_sku,
            "substitute_note": note,
            "substitute_kind": kind,
        })
    return written


def products_by_label() -> dict[str, list[dict]]:
    """Catalog products grouped by the vision label they present as."""
    grouped: dict[str, list[dict]] = {}
    for product in db.list_products():
        label = product.get("detected_as")
        if label:
            grouped.setdefault(label, []).append(product)
    return grouped


def choose_product(rng: random.Random, label: str, grouped: dict[str, list[dict]]) -> dict | None:
    """Picks which catalog variant a disposal of `label` was.

    Several products can share a label because the label alone cannot
    separate them; the pick is weighted by VARIANT_WEIGHTS so the demo's
    variant mix looks like a campus that buys more of the cheap bottle than
    the premium one. Returns None for a label the catalog deliberately does
    not cover.
    """
    candidates = grouped.get(label)
    if not candidates:
        fallback_sku = GENERIC_LABEL_FALLBACK.get(label)
        if fallback_sku is None:
            return None
        for products in grouped.values():
            for product in products:
                if product["sku"] == fallback_sku:
                    return product
        return None
    if len(candidates) == 1:
        return candidates[0]
    weights = [VARIANT_WEIGHTS.get(product["sku"], 1) for product in candidates]
    return rng.choices(candidates, weights=weights, k=1)[0]


def attribute_events() -> tuple[int, int]:
    """Points unattributed disposal events at a catalog product.

    Only events with no PRODUCT_ID are touched, so an event the live pipeline
    matched by image embedding keeps that match. Every row written here is
    stamped MATCH_METHOD = 'seeded', which is what lets the analytics page
    report how much of its cost total rests on demo attribution rather than
    on a real match.

    Returns (attributed, left_unmatched).
    """
    rng = random.Random(RANDOM_SEED + 1)
    grouped = products_by_label()
    pending = db.list_unattributed_events()

    updates = []
    unmatched = 0
    for event_id, detected_object in pending:
        if not detected_object:
            unmatched += 1
            continue
        product = choose_product(rng, detected_object, grouped)
        if product is None:
            unmatched += 1
            continue
        updates.append({
            "event_id": event_id,
            "product_id": product["product_id"],
            "match_method": "seeded",
        })

    return db.set_event_product_matches(updates), unmatched


def review_verdict(rng: random.Random, confidence: float | None) -> bool:
    """Whether the reviewer agreed with the classification.

    Agreement rises with the model's own confidence, which is what makes the
    calibration chart on the analytics page show a real relationship. A
    classifier whose errors were spread evenly across confidence would be
    one whose confidence means nothing -- true of some models, but not a
    useful thing to fabricate.
    """
    if confidence is None:
        return rng.random() < BASE_AGREEMENT
    # 62% confidence -> ~0.78 agreement; 95% -> ~0.97.
    scaled = 0.78 + (max(62.0, min(95.0, confidence)) - 62.0) / 33.0 * 0.19
    return rng.random() < scaled


def seed_reviews() -> int:
    """Adds human verdicts for a sample of events that have none.

    Coverage is deliberately partial (REVIEW_COVERAGE): a review trail over
    every event would be the tell that it is fictional, and the analytics
    page reports the reviewed fraction next to the accuracy figure precisely
    so a rate over a small sample cannot pass as a rate over all of them.
    """
    rng = random.Random(RANDOM_SEED + 2)
    confusable_by_seen: dict[str, list[tuple]] = {}
    for seen, actual, seen_cat, actual_cat in CONFUSABLE:
        confusable_by_seen.setdefault(seen, []).append((actual, actual_cat))

    candidates = db.list_unreviewed_events()
    rows = []
    for event_id, detected_object, category, confidence, created_at in candidates:
        if rng.random() > REVIEW_COVERAGE:
            continue

        agreed = review_verdict(rng, float(confidence) if confidence is not None else None)
        corrections = confusable_by_seen.get(detected_object or "")
        if agreed or not corrections:
            rows.append({
                "event_id": event_id,
                "verdict": "correct",
                "corrected_category": None,
                "corrected_object": None,
                "reviewer": rng.choice(REVIEWERS),
                # Reviews happen after the fact, not at capture time.
                "reviewed_at": created_at + timedelta(hours=rng.uniform(1.0, 48.0)),
                "notes": None,
            })
            continue

        corrected_object, corrected_category = rng.choice(corrections)
        rows.append({
            "event_id": event_id,
            "verdict": "incorrect",
            "corrected_category": corrected_category if corrected_category != category else None,
            "corrected_object": corrected_object,
            "reviewer": rng.choice(REVIEWERS),
            "reviewed_at": created_at + timedelta(hours=rng.uniform(1.0, 48.0)),
            "notes": f"Logged as {detected_object!r}; actually {corrected_object!r}",
        })

    return db.insert_event_reviews(rows)


def main() -> None:
    reseed_reviews = "--reseed-reviews" in sys.argv
    fix_confidence = "--normalize-confidence" in sys.argv

    print("Seeding supplies catalog and review trail.")
    print("  COSTS AND MASSES ARE DEMO DATA -- see module docstring.")

    if fix_confidence:
        print(f"  confidence:      {db.normalize_confidence_scale()} row(s) rescaled to 0-100")

    inserted, present = seed_products()
    print(f"  products:        {inserted} new, {present} already present")
    print(f"  legacy filled:   {complete_legacy_products()} column(s) on pre-002 rows")
    print(f"  reusables:       {seed_reusable_programmes()} new programme(s)")
    print(f"  substitutions:   {apply_substitutions()} column(s) recorded")

    attributed, unmatched = attribute_events()
    print(f"  attributed:      {attributed} event(s) matched to a product")
    print(f"  unmatched:       {unmatched} event(s) left with no catalog match")

    if reseed_reviews or db.count_event_reviews() == 0:
        print(f"  reviews:         {seed_reviews()} new verdict(s)")
    else:
        print(f"  reviews:         {db.count_event_reviews()} already present "
              f"(pass --reseed-reviews to add more)")

    print("Done.")


if __name__ == "__main__":
    main()
