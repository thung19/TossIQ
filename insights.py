"""Rule-based waste insights, generated from actual logged WASTE_EVENTS data.

Deliberately simple threshold rules rather than a learned model -- PRD
section 2E requires recommendations to "reference underlying observations
rather than being generic sustainability advice", which a few targeted SQL
aggregations satisfy without extra ML infrastructure (section 9: "Do not
add unnecessary infrastructure").

Where purchasing/inventory data isn't available (it never is for this MVP),
recommendations are phrased as "consider investigating" rather than a
definitive forecast, per PRD section 2E.
"""

import db

FREQUENT_ITEM_THRESHOLD = 3      # same item discarded this many times -> flag it
LOCATION_SPIKE_THRESHOLD = 5     # one (location, category) pair this many times -> flag it
HIGH_VALUE_UNIT_COST = 5.0       # catalog unit_cost above this counts as "potentially valuable"


def generate_recommendations(days: int = 30) -> list[str]:
    """Computes fresh recommendations from current data and persists any new ones.

    Returns the newly generated recommendation texts (empty if nothing meets
    the thresholds yet -- an empty, low-volume demo dataset should not
    produce fabricated insights).
    """
    candidates = []
    candidates.extend(_frequent_item_recommendations(days))
    candidates.extend(_location_category_spike_recommendations(days))
    candidates.extend(_high_value_discard_recommendations(days))
    candidates.extend(_hazard_flag_recommendations(days))

    existing = {r["text"] for r in db.list_recommendations(limit=200)}
    new_texts = [text for text in candidates if text not in existing]
    for text in new_texts:
        db.insert_recommendation(text)
    return new_texts


def _frequent_item_recommendations(days: int) -> list[str]:
    items = db.stats_items(days=days)
    out = []
    for item in items:
        if item["count"] >= FREQUENT_ITEM_THRESHOLD:
            name = item["matched_product"] or item["detected_object"]
            out.append(
                f"'{name}' was discarded {item['count']} times in the last {days} days. "
                "Consider investigating whether this reflects over-purchasing, over-preparation, "
                "or a reusable alternative that could reduce this volume."
            )
    return out


def _location_category_spike_recommendations(days: int) -> list[str]:
    rows = db.stats_locations(days=days)
    out = []
    for row in rows:
        if row["count"] >= LOCATION_SPIKE_THRESHOLD and row["location"] != "unspecified":
            out.append(
                f"Location '{row['location']}' logged {row['count']} {row['category']} disposals "
                f"in the last {days} days -- an unusually high concentration worth reviewing for "
                "that location's purchasing or operational practices."
            )
    return out


def _high_value_discard_recommendations(days: int) -> list[str]:
    items = db.stats_items(days=days)
    out = []
    for item in items:
        if item["estimated_value"] is not None and item["estimated_value"] >= HIGH_VALUE_UNIT_COST:
            name = item["matched_product"] or item["detected_object"]
            out.append(
                f"Catalog item '{name}' has an estimated ${item['estimated_value']:.2f} in disposed "
                f"value over the last {days} days. Flag for review as potentially recoverable or "
                "reusable inventory rather than waste."
            )
    return out


def _hazard_flag_recommendations(days: int) -> list[str]:
    events = db.list_hazard_events(days=days)
    out = []
    for event in events:
        out.append(
            f"A potentially hazardous item ('{event['detected_object']}') was flagged for review "
            f"at '{event['location']}' on {event['date']}: {event['hazard_reason']}. "
            "Recommend manual inspection before further handling."
        )
    return out
