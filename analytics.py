"""Shaping layer for the analytics page.

Same contract as fleet.py: this module owns the derivation, the frontend
renders what it is handed. A cost total, a mass estimate and an accuracy rate
are each computed once, here, so the figure on the materials tab and the
figure on the supplier tab cannot drift apart.

Three things are worth reading before trusting a number out of this module.

Mass is always an estimate. No can has a weight sensor -- CLAUDE.md records
that as a hard hardware constraint -- so every gram reported here is
(items counted) x (the catalog's reference mass for that product). It is
labelled `estimated_grams` everywhere, never `weight`, and the provenance
block says how much of it rests on a specific product versus a class
average.

Cost is the loss from discarding, not the purchase price. The catalog
records 0.00 for consumed residue: a banana peel represents no loss, because
the banana was eaten. Uneaten food and whole discarded units carry their real
value. An item the catalog does not cover carries no cost at all and is
counted in `no_cost_items` rather than silently treated as free.

Accuracy means agreement with a human reviewer, and only a minority of events
are reviewed. Every accuracy figure travels with the sample it was computed
over, so a 92% over 153 reviews can never be read as a 92% over 1,031 events.
"""

import db

# Tiers a cost or mass figure can rest on, worst to best. Reported alongside
# every total so a reader can tell a hard number from a modelled one.
#   matched  -- the event is tied to a specific catalog product.
#   class    -- the product is unknown but its vision label is in the catalog,
#               so the average across that label's variants is used.
#   none     -- the catalog does not cover this label at all.
PROVENANCE_TIERS = ("matched", "class", "none")

# Which disposal categories count as diverted from landfill.
DIVERTED_CATEGORIES = {"recycling", "compost"}

# Confidence buckets for the calibration view, as (lower_bound_inclusive,
# label). A classifier is well calibrated when accuracy climbs across these.
CONFIDENCE_BUCKETS = ((0, "<60%"), (60, "60-69%"), (70, "70-79%"), (80, "80-89%"), (90, "90%+"))


def _measures(row: dict) -> dict:
    """Turns one raw grouped row into the measure block the API serves."""
    count = row["n"]
    matched = row["matched_n"]
    estimated_cost = row["matched_cost"] + row["class_cost"]
    estimated_grams = row["matched_grams"] + row["class_grams"]
    return {
        "count": count,
        "matched_count": matched,
        "estimated_cost": round(estimated_cost, 2),
        "estimated_grams": round(estimated_grams, 1),
        "estimated_kg": round(estimated_grams / 1000.0, 3),
        # The share of this group's money that comes from a specific product
        # rather than a class average. A cost built mostly from averages is
        # still worth showing, but not worth acting on without saying so.
        "cost_from_matched": round(row["matched_cost"], 2),
        "cost_from_class_average": round(row["class_cost"], 2),
        "no_cost_items": row["no_cost_n"],
        # Hazards travel with every breakdown rather than living only on
        # their own page: "which building throws away the most" and "which
        # building throws away the most dangerous things" are different
        # questions, and the second one should not need a different tab.
        "hazard_items": row.get("hazard_n", 0),
        "hazard_critical_items": row.get("hazard_critical_n", 0),
        "avg_confidence": round(row["avg_confidence"], 1) if row["avg_confidence"] else None,
    }


def distribution(
    dimension: str,
    limit: int | None = 40,
    **filters,
) -> dict:
    """Counts, cost and estimated mass grouped by one dimension.

    This backs every "distribution of X" view. `share` is computed against
    the total of the rows returned, and `truncated` says whether a limit cut
    the tail off, so a pie chart cannot quietly add up to less than 100%.
    """
    rows = db.analytics_distribution(dimension, limit=limit, **filters)
    shaped = [{"bucket": row["bucket"], **_measures(row)} for row in rows]
    total_count = sum(row["count"] for row in shaped)
    for row in shaped:
        row["share"] = round(100.0 * row["count"] / total_count, 1) if total_count else 0.0

    grand = db.analytics_totals(**filters)
    return {
        "dimension": dimension,
        "rows": shaped,
        "shown_count": total_count,
        "total_count": grand["n"],
        "truncated": grand["n"] > total_count,
    }


def overview(**filters) -> dict:
    """The headline block: volume, money, estimated mass, diversion, and how
    much of each rests on a real catalog match."""
    totals = db.analytics_totals(**filters)
    by_category = db.analytics_distribution("category", limit=None, **filters)

    counts = {row["bucket"]: row["n"] for row in by_category}
    total = totals["n"]
    diverted = sum(count for name, count in counts.items() if name in DIVERTED_CATEGORIES)

    measures = _measures(totals)
    matched_share = round(100.0 * totals["matched_n"] / total, 1) if total else 0.0

    return {
        **measures,
        "total_items": total,
        "by_category": [{"category": row["bucket"], **_measures(row)} for row in by_category],
        "diverted_items": diverted,
        "diversion_rate": round(100.0 * diverted / total, 1) if total else 0.0,
        "catalog_match_rate": matched_share,
        "hazard_rate": round(100.0 * totals.get("hazard_n", 0) / total, 2) if total else 0.0,
        # Everything above that is an estimate rather than a count, named so
        # the UI can caption it without hardcoding the caveat in three places.
        "estimate_notes": {
            "mass": "Items x catalog reference mass. No can has a weight sensor; "
                    "no mass here is measured.",
            "cost": "Loss from discarding, per the catalog. Consumed residue "
                    "(peels, cores, spent grounds) is 0.00 because the product "
                    "was used; uneaten food and whole discarded units carry "
                    "their value.",
            "unmatched": f"{totals['no_cost_n']} item(s) have no catalog entry and "
                         f"contribute to neither total.",
            "hazards": (
                f"{totals.get('hazard_n', 0)} item(s) in this scope were flagged as "
                f"hazardous, {totals.get('hazard_critical_n', 0)} of them critical. "
                "Hazards carry no catalog cost and belong in no bin the sorter has: "
                "there is nowhere correct to put them, which is the point."
            ),
        },
    }


def hotspots(limit: int = 15, **filters) -> dict:
    """Where the volume is: by building, by campus area, and by can."""
    return {
        "by_building": [
            {"bucket": row["bucket"], **_measures(row)}
            for row in db.analytics_distribution("building", limit=limit, **filters)
        ],
        "by_campus_area": [
            {"bucket": row["bucket"], **_measures(row)}
            for row in db.analytics_distribution("campus_area", limit=limit, **filters)
        ],
        "by_can": [
            {"bucket": row["bucket"], **_measures(row)}
            for row in db.analytics_distribution("can", limit=limit, **filters)
        ],
    }


def bin_composition(top_items_per_can: int = 5, **filters) -> list[dict]:
    """What is usually in each can, as one row per can with its top items."""
    rows = db.analytics_bin_composition(top_items_per_can=top_items_per_can, **filters)
    by_can: dict[int, dict] = {}
    for row in rows:
        entry = by_can.setdefault(row["can_id"], {
            "can_id": row["can_id"],
            "can_code": row["can_code"],
            "building_name": row["building_name"],
            "items": [],
            "shown_items": 0,
        })
        entry["items"].append({
            "item": row["item"],
            "category": row["category"],
            "count": row["count"],
            "estimated_cost": round(row["estimated_cost"], 2),
        })
        entry["shown_items"] += row["count"]
    return sorted(by_can.values(), key=lambda entry: entry["shown_items"], reverse=True)


def misrouted(limit: int = 20, **filters) -> dict:
    """Items put in a bin the catalog says is the wrong one.

    Both sides are recorded facts -- the bin the item went into, and the bin
    its catalog entry says it belongs in -- so each row is a genuine
    disagreement rather than a model opinion. That makes it the one quality
    signal on this page that needs no human reviewer.
    """
    rows = db.analytics_misrouted(limit=limit, **filters)
    total = db.analytics_totals(**filters)["n"]
    misrouted_count = sum(row["count"] for row in rows)
    return {
        "rows": [
            {**row, "estimated_kg": round(row["grams"] / 1000.0, 3)}
            for row in rows
        ],
        "misrouted_count": misrouted_count,
        "total_items": total,
        "misrouted_rate": round(100.0 * misrouted_count / total, 1) if total else 0.0,
        "note": "Compares the bin an item was logged into against the bin its catalog "
                "entry says it belongs in. Only items matched to the catalog can "
                "be checked.",
    }


def accuracy(**filters) -> dict:
    """Agreement between the classifier and a human reviewer.

    Deliberately not derived from model confidence: confidence is the model
    grading its own homework, and a dashboard that reports it as accuracy is
    reporting nothing. This reads EVENT_REVIEWS, reports the sample size
    everywhere, and says plainly when the sample is too small to support a
    per-category rate.
    """
    reviews = db.analytics_review_rows(**filters)
    total_events = db.analytics_totals(**filters)["n"]
    reviewed = len(reviews)
    correct = sum(1 for row in reviews if row["verdict"] == "correct")

    # Per-category agreement, from the category the model assigned.
    per_category: dict[str, dict] = {}
    for row in reviews:
        name = row["category"] or "unknown"
        entry = per_category.setdefault(name, {"category": name, "reviewed": 0, "correct": 0})
        entry["reviewed"] += 1
        entry["correct"] += row["verdict"] == "correct"

    # Confidence calibration: does the model's own confidence predict whether
    # a human agreed with it?
    buckets = [
        {"label": label, "lower": lower, "reviewed": 0, "correct": 0}
        for lower, label in CONFIDENCE_BUCKETS
    ]
    unscored = 0
    for row in reviews:
        if row["confidence"] is None:
            unscored += 1
            continue
        target = buckets[0]
        for bucket in buckets:
            if row["confidence"] >= bucket["lower"]:
                target = bucket
        target["reviewed"] += 1
        target["correct"] += row["verdict"] == "correct"

    # The specific mistakes, as (what it said) -> (what it was).
    confusions: dict[tuple, int] = {}
    for row in reviews:
        if row["verdict"] == "correct":
            continue
        key = (row["detected_object"] or "unidentified", row["corrected_object"] or "unspecified")
        confusions[key] = confusions.get(key, 0) + 1

    return {
        "reviewed_events": reviewed,
        "total_events": total_events,
        "review_coverage": round(100.0 * reviewed / total_events, 1) if total_events else 0.0,
        "correct": correct,
        "accuracy": round(100.0 * correct / reviewed, 1) if reviewed else None,
        "by_category": sorted(
            (
                {**entry, "accuracy": round(100.0 * entry["correct"] / entry["reviewed"], 1)}
                for entry in per_category.values()
            ),
            key=lambda entry: entry["reviewed"],
            reverse=True,
        ),
        "calibration": [
            {**bucket,
             "accuracy": round(100.0 * bucket["correct"] / bucket["reviewed"], 1)
             if bucket["reviewed"] else None}
            for bucket in buckets
        ],
        "unscored_reviews": unscored,
        "confusions": sorted(
            (
                {"seen_as": seen, "actually_was": actual, "count": count}
                for (seen, actual), count in confusions.items()
            ),
            key=lambda entry: entry["count"],
            reverse=True,
        )[:15],
        "note": "Accuracy is agreement with a human reviewer, over the reviewed "
                "sample only. It is not derived from model confidence.",
    }


def catalog_rollup(limit: int = 60, **filters) -> dict:
    """The supplies view: what is being thrown away, by SKU and supplier.

    This is the join the purchasing conversation needs -- a SKU, its supplier,
    its case pack and case cost, and how many units of it the bins have seen.
    `cases_equivalent` converts the count into the unit purchasing actually
    orders in, which is what makes "order one case less of this" a sentence
    someone can act on.
    """
    products = {product["sku"]: product for product in db.list_products()}
    rows = db.analytics_distribution("sku", limit=limit, **filters)

    shaped = []
    for row in rows:
        sku = row["bucket"]
        product = products.get(sku)
        measures = _measures(row)
        pack = product.get("case_pack_qty") if product else None
        shaped.append({
            "sku": sku,
            "product_name": product["product_name"] if product else None,
            "brand": product.get("brand") if product else None,
            "variant_label": product.get("variant_label") if product else None,
            "supplier": product.get("supplier") if product else None,
            "material": product.get("material") if product else None,
            "material_subtype": product.get("material_subtype") if product else None,
            "unit_cost": product.get("unit_cost") if product else None,
            "unit_weight_grams": product.get("unit_weight_grams") if product else None,
            "correct_bin": product.get("disposal_category") if product else None,
            "recyclable": product.get("recyclable") if product else None,
            "case_pack_qty": pack,
            "case_cost": product.get("case_cost") if product else None,
            "cases_equivalent": round(measures["count"] / pack, 2) if pack else None,
            **measures,
        })

    by_supplier = [
        {"bucket": row["bucket"], **_measures(row)}
        for row in db.analytics_distribution("supplier", limit=None, **filters)
    ]
    return {
        "skus": shaped,
        "by_supplier": by_supplier,
        "catalog_size": len(products),
    }
