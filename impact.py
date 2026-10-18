"""Environmental impact estimates for discarded items.

Some recommendations are not worth making on money. Swapping a polypropylene
straw for a paper one costs MORE per unit; the case for it is entirely
environmental, and a page that ranks only by dollars would either bury it or,
worse, argue against it. This module supplies the other axis.

Two different quantities, kept apart because they answer different questions
and must never be added together:

  * AVOIDED PRODUCTION -- the embodied carbon of an item you stop buying at
    all. Installing refill stations so 876 bottles a year are never purchased
    avoids the carbon of making 876 bottles.
  * DIVERTED FROM LANDFILL -- the benefit of sending the same item down a
    better stream. You still made the thing; you just stopped burying it.

Both are ESTIMATES built from catalog reference masses, which are themselves
estimates: no can has a weight sensor. Every figure that leaves this module
is labelled as such.

!! THE FACTORS BELOW ARE ILLUSTRATIVE !!
They are order-of-magnitude values consistent with published life-cycle
inventory ranges, chosen so the relative weighting between materials is
sensible -- aluminium an order above paper, food waste dominated by its
upstream agriculture. They are NOT drawn from a verified LCA database and
must be replaced with factors from one (DEFRA, EPA WARM, ecoinvent) before
any figure here is reported externally.
"""

# kg CO2e per kg of material, for producing it in the first place.
EMBODIED_CO2E_PER_KG = {
    "plastic": 2.4,
    "bioplastic": 2.0,
    "paper": 1.1,
    "fibre": 1.0,
    "glass": 0.9,
    "metal": 6.5,
    "ceramic": 1.2,
    "textile": 15.0,
    "organic": 2.5,   # upstream agriculture, which is why food waste dominates
}

# Finer-grained overrides where the subtype matters more than the family.
# Aluminium is far above steel; EPS far above other plastics.
EMBODIED_CO2E_BY_SUBTYPE = {
    "aluminium": 9.0,
    "tinplate steel": 2.0,
    "EPS": 3.4,
    "PET": 2.2,
    "PP": 1.9,
    "PS": 2.7,
    "nitrile": 5.5,
    "metallised BOPP": 3.1,
    "multilayer film": 3.1,
    "corrugated": 0.9,
    "corrugated kraft": 0.9,
    "tissue": 1.2,
    "edible food": 3.5,
    "fruit residue": 0.6,
    "spent grounds": 0.4,
    "green waste": 0.2,
}

# kg CO2e avoided per kg moved out of landfill into the right stream.
# Compost's figure is avoided landfill methane, which is why organics gain
# the most from being diverted even though their embodied carbon is counted
# separately.
DIVERSION_CO2E_PER_KG = {
    "compost": 0.60,
    "recycling": 0.45,
    "landfill": 0.0,
}

DISCLAIMER = (
    "Carbon figures are estimates: catalog reference mass times an "
    "illustrative emission factor. Replace the factors with a verified LCA "
    "source before reporting any of this externally."
)


def embodied_factor(material: str | None, subtype: str | None) -> float:
    """kg CO2e per kg, preferring the subtype where one is known.

    Returns 0.0 for an unrecognised material rather than a guess: a missing
    factor should make a recommendation look smaller than it is, never
    larger.
    """
    if subtype and subtype in EMBODIED_CO2E_BY_SUBTYPE:
        return EMBODIED_CO2E_BY_SUBTYPE[subtype]
    if material and material in EMBODIED_CO2E_PER_KG:
        return EMBODIED_CO2E_PER_KG[material]
    return 0.0


def avoided_production_co2e(product: dict, units: float) -> float:
    """kg CO2e not emitted because `units` of this product were never made."""
    grams = product.get("unit_weight_grams") or 0.0
    factor = embodied_factor(product.get("material"), product.get("material_subtype"))
    return grams * units / 1000.0 * factor


def diversion_co2e(grams: float, to_stream: str | None) -> float:
    """kg CO2e avoided by moving `grams` out of landfill into `to_stream`."""
    return grams / 1000.0 * DIVERSION_CO2E_PER_KG.get(to_stream or "landfill", 0.0)


def switch_co2e(current: dict, replacement: dict, units: float) -> dict:
    """The carbon difference between buying `units` of one product and the
    equivalent service from another.

    Both halves are reported rather than only the net, because a switch can
    be worse on production and better on disposal -- a compostable fibre
    clamshell is heavier than the PET one it replaces -- and a single net
    number would hide the trade rather than show it.
    """
    current_units = units
    # A reusable delivers many services per unit, so far fewer are produced.
    uses = max(1, replacement.get("expected_uses") or 1)
    replacement_units = units / uses

    current_production = avoided_production_co2e(current, current_units)
    replacement_production = avoided_production_co2e(replacement, replacement_units)

    current_grams = (current.get("unit_weight_grams") or 0.0) * current_units
    replacement_grams = (replacement.get("unit_weight_grams") or 0.0) * replacement_units

    current_diversion = diversion_co2e(current_grams, current.get("disposal_category"))
    replacement_diversion = diversion_co2e(replacement_grams, replacement.get("disposal_category"))

    return {
        "production_saved_kg": round(current_production - replacement_production, 1),
        "diversion_gained_kg": round(replacement_diversion - current_diversion, 1),
        "net_co2e_kg": round(
            (current_production - replacement_production)
            + (replacement_diversion - current_diversion),
            1,
        ),
        "landfill_avoided_kg": round(
            (
                (current_grams if current.get("disposal_category") == "landfill" else 0.0)
                - (replacement_grams if replacement.get("disposal_category") == "landfill" else 0.0)
            )
            / 1000.0,
            1,
        ),
        "units_avoided": round(current_units - replacement_units),
    }


def describe_co2e(kilograms: float) -> str:
    """A kg CO2e figure in units a reader has a feel for.

    Tonnes above a tonne; otherwise kilograms. No car-miles or tree
    equivalents: those conversions carry their own uncertainty and stack it
    on top of factors already labelled illustrative.
    """
    if abs(kilograms) >= 1000:
        return f"{kilograms / 1000:.1f} t CO2e"
    return f"{kilograms:.0f} kg CO2e"
