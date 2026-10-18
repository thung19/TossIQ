"""Structured, evidence-carrying recommendations for the operator.

The difference between this module and insights.py is the evidence. insights
emits sentences; every recommendation here carries the observations it was
derived from, as typed blocks the UI renders under the card. That is the
whole point: an operator asked to buy 400 ceramic mugs should be able to see
the 1,247 paper cups, the cost-per-use arithmetic and the payback month
before agreeing, not just a confident sentence.

Rules are thresholds over logged data, not a model. Each one states its own
basis and its own caveats, and none fires on a sample too small to mean
anything -- an empty demo database produces no recommendations rather than
fabricated ones.

Two things every money figure here obeys:

  * A saving is a PROJECTION from a window, and is labelled as one. Thirty
    days of cups extrapolated to a year assumes next year looks like last
    month, which for a university with a summer is not quite true; the
    caveat travels with the number.
  * Cost of a disposable is its catalog price. Cost of a reusable is its
    price over its rated service life plus washing. WASH_COST_PER_USE is the
    one number here with no source in the data, so it is a named constant,
    surfaced in the evidence, and easy to argue with.
"""

import db
import fleet

# Dish-machine labour, water, energy and detergent per item, per the sort of
# figure campus dining operations publish. It is an ASSUMPTION, not an
# observation, and the recommendation shows it so the reader can substitute
# their own. Reusables stop paying back above roughly $0.09/use here.
WASH_COST_PER_USE = 0.04

# No rule fires below this many observations. A recommendation drawn from
# four disposals is noise wearing a suit.
MIN_OBSERVATIONS = 8

# A building needs its typical can to be this many times the campus-wide
# typical can before more bins are the answer.
CAN_PRESSURE_RATIO = 1.6

# Share of a can's disposals that must fall inside one six-hour block before
# its collection round is worth moving. At 0.45 almost every can qualified --
# a six-hour window is a quarter of the day, and any bin with a normal
# daytime rhythm clears that bar, so it flagged the pattern rather than the
# exception.
PEAK_CONCENTRATION = 0.58

# A route needs this many cans before it is a route rather than a detour.
MIN_ROUTE_CANS = 3

# Fill at or above this on the current reading, for a can also emptied less
# often than its volume warrants.
SERVICE_PRESSURE_PERCENT = 80.0


# ---------------------------------------------------------------------------
# Evidence blocks
# ---------------------------------------------------------------------------
# Three shapes, because three is what the data needs and a fourth would be a
# chart nobody asked for. Each carries its own caption: the evidence has to
# explain itself when read on its own, under a card, away from this code.

def metric(label: str, value: str, caption: str | None = None) -> dict:
    return {"type": "metric", "label": label, "value": value, "caption": caption}


def table(label: str, columns: list[str], rows: list[list], caption: str | None = None) -> dict:
    return {"type": "table", "label": label, "columns": columns, "rows": rows, "caption": caption}


def bars(label: str, rows: list[dict], caption: str | None = None) -> dict:
    """rows: [{"bucket": str, "value": float, "note": str | None}]"""
    return {"type": "bars", "label": label, "rows": rows, "caption": caption}


def recommendation(
    key: str,
    kind: str,
    title: str,
    summary: str,
    action: str,
    evidence: list[dict],
    basis: str,
    window_days: int,
    annual_saving: float | None = None,
    confidence: str = "medium",
    caveat: str | None = None,
) -> dict:
    """One recommendation.

    `key` is a stable slug built from what the rule matched, not a counter,
    so the same finding keeps the same identity across refreshes and a link
    to it survives the next run.
    """
    return {
        "key": key,
        "kind": kind,
        "title": title,
        "summary": summary,
        "action": action,
        "evidence": evidence,
        "basis": basis,
        "window_days": window_days,
        "annual_saving": round(annual_saving, 2) if annual_saving is not None else None,
        "confidence": confidence,
        "caveat": caveat,
    }


def _annualise(value: float, window_days: int) -> float:
    return value / max(1, window_days) * 365.0


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    """"1 can" / "3 cans". Worth a helper because these strings are the
    product: a recommendation that says "Empty the 1 cans" reads as broken
    software, and a reader who notices that stops trusting the number
    beside it."""
    word = singular if count == 1 else (plural or singular + "s")
    return f"{count} {word}"


def _mass(grams: float) -> str:
    """Grams below a kilo. "0.0 kg sent down the wrong stream" is a true
    statement that reads as a bug and tells the reader nothing."""
    if grams >= 1000:
        return f"{grams / 1000:.1f} kg"
    return f"{grams:.0f} g"


def _plain_item(name: str) -> str:
    """Catalog names carry a disambiguating parenthetical -- "Pizza Crust
    (uneaten)" -- which is right in a table and wrong mid-sentence."""
    return name.split(" (")[0].strip()


# ---------------------------------------------------------------------------
# Shared context
# ---------------------------------------------------------------------------
# db.py opens a connection per call, which is right for the API's single-row
# writes and wrong for a page that runs six rules over four overlapping
# queries. Before this, fleet.list_fleet() alone was fetched three times --
# once each by the capacity, schedule and backlog rules -- and the endpoint
# took 3.5 s, nearly all of it connection setup. Everything shared is
# gathered once here and handed to the rules.

def build_context(days: int) -> dict:
    return {
        "days": days,
        "products": {p["sku"]: p for p in db.list_products()},
        "fleet": fleet.list_fleet(),
        "by_sku": db.analytics_distribution("sku", days=days, limit=None),
        "by_can": db.analytics_distribution("can", days=days, limit=None),
        "activity": fleet.activity_heatmap(days=min(days, 30)),
        "edible_food": db.edible_food_waste(days=days),
        "misrouted": db.analytics_misrouted(days=days, limit=40),
    }


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
# Each takes the shared context and returns zero or more recommendations.
# None of them query directly, so adding a rule costs no round trips unless
# it genuinely needs data nothing else uses.

def switch_to_reusable(context: dict) -> list[dict]:
    """Disposables being thrown away in volume that the catalog names a
    reusable replacement for.

    The arithmetic is cost per use on both sides, not sticker price: a $4.20
    mug is more expensive than an $0.11 cup exactly once, and the crossover
    is what the operator needs to see.
    """
    days = context["days"]
    out = []
    products = context["products"]
    rows = context["by_sku"]

    for row in rows:
        product = products.get(row["bucket"])
        if not product or not product.get("substitute_sku"):
            continue
        replacement = products.get(product["substitute_sku"])
        if not replacement or not replacement.get("reusable"):
            continue

        count = row["n"]
        if count < MIN_OBSERVATIONS:
            continue

        disposable_per_use = product["unit_cost"] or 0.0
        uses = replacement.get("expected_uses") or 1
        reusable_per_use = (replacement["unit_cost"] or 0.0) / uses + WASH_COST_PER_USE
        saving_per_use = disposable_per_use - reusable_per_use
        if saving_per_use <= 0:
            continue

        annual_units = _annualise(count, days)
        annual_saving = annual_units * saving_per_use
        # One reusable unit covers a day's turns; a fleet sized to the daily
        # peak is the honest capital figure, not one unit per annual use.
        daily_units = count / max(1, days)
        fleet_size = max(1, round(daily_units * 1.5))
        upfront = fleet_size * (replacement["unit_cost"] or 0.0)
        payback_months = (upfront / annual_saving * 12) if annual_saving > 0 else None

        out.append(recommendation(
            key=f"reusable:{product['sku']}",
            kind="procurement",
            title=f"Replace {product['product_name']} with the {replacement['product_name']}",
            summary=(
                f"{count} units went in the bin over {days} days. At "
                f"{_money(disposable_per_use)} each against "
                f"{_money(reusable_per_use)} per use for the reusable, the switch "
                f"saves about {_money(annual_saving)} a year."
            ),
            action=(
                f"Pilot {_plural(fleet_size, 'unit')} of {replacement['sku']} "
                f"({_money(upfront)} up front) in the highest-volume building first."
            ),
            annual_saving=annual_saving,
            confidence="high" if count >= MIN_OBSERVATIONS * 4 else "medium",
            window_days=days,
            basis=(
                f"Counted from disposals matched to {product['sku']} in WASTE_EVENTS "
                f"over {days} days, priced from the PRODUCTS catalog."
            ),
            caveat=(
                f"Washing is assumed at {_money(WASH_COST_PER_USE)} per use, the one "
                "figure here not measured from your data. "
                + (product.get("substitute_note") or "")
            ),
            evidence=[
                metric("Units discarded", f"{count:,}", f"over the last {days} days"),
                metric("Projected annual units", f"{annual_units:,.0f}",
                       "straight-line from the window above"),
                metric("Projected annual saving", _money(annual_saving),
                       "difference in cost per use, times annual units"),
                metric("Payback", f"{payback_months:.1f} months" if payback_months else "—",
                       f"{fleet_size} units at {_money(replacement['unit_cost'] or 0)} each"),
                table(
                    "Cost per use",
                    ["", "unit price", "uses per unit", "washing", "cost per use"],
                    [
                        [product["product_name"], _money(disposable_per_use), "1", "—",
                         _money(disposable_per_use)],
                        [replacement["product_name"], _money(replacement["unit_cost"] or 0),
                         f"{uses:,}", _money(WASH_COST_PER_USE), _money(reusable_per_use)],
                    ],
                    "Catalog prices. The reusable amortises its price over its rated "
                    "service life, then pays washing on every use.",
                ),
                table(
                    "Disposal footprint avoided",
                    ["measure", "value"],
                    [
                        ["Stream today", product.get("disposal_category") or "unknown"],
                        ["Estimated mass discarded",
                         f"{(product.get('unit_weight_grams') or 0) * count / 1000:.1f} kg"],
                        ["Supplier", product.get("supplier") or "—"],
                    ],
                    "Mass is items times the catalog reference weight; nothing is weighed.",
                ),
            ],
        ))

    out.sort(key=lambda r: r["annual_saving"] or 0, reverse=True)
    return out


def add_or_relocate_cans(context: dict) -> list[dict]:
    """Buildings whose typical can absorbs far more than the campus norm.

    Compares each building's MEDIAN can against the campus median can, not
    its total. A total is dominated by one busy unit -- the library's live
    camera logged a 294-item burst into a single can -- and would recommend
    hardware for a building that simply has one popular bin.
    """
    days = context["days"]
    per_can = context["by_can"]
    cans = {can["can_code"]: can for can in context["fleet"]}

    by_building: dict[str, list[tuple[str, int]]] = {}
    for row in per_can:
        can = cans.get(row["bucket"])
        if not can:
            continue
        by_building.setdefault(can["building_name"], []).append((row["bucket"], row["n"]))

    def median(values: list[int]) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return float(ordered[middle])
        return (ordered[middle - 1] + ordered[middle]) / 2.0

    campus_median = median([count for rows in by_building.values() for _, count in rows])
    if campus_median <= 0:
        return []

    out = []
    for building, rows in by_building.items():
        counts = [count for _, count in rows]
        # A building with a single can has no typical can to speak of: its
        # median is that one can, so the comparison would be the very
        # one-busy-bin artefact the median exists to filter out.
        if len(rows) < 2 or sum(counts) < MIN_OBSERVATIONS * 3:
            continue
        building_median = median(counts)
        ratio = building_median / campus_median
        if ratio < CAN_PRESSURE_RATIO:
            continue

        out.append(recommendation(
            key=f"capacity:{building}",
            kind="placement",
            title=f"Add a bin at {building}",
            summary=(
                f"The typical can here took {building_median:.0f} items over {days} days "
                f"against a campus typical of {campus_median:.0f} -- {ratio:.1f}x the norm, "
                f"across {_plural(len(rows), 'can')} rather than one busy one."
            ),
            action=(
                f"Site one additional can at {building}, or relocate an under-used unit "
                "from a quieter building before buying hardware."
            ),
            confidence="high" if len(rows) >= 3 else "low",
            window_days=days,
            basis=(
                "Median items per can per building, from disposals attributed to a can "
                "in WASTE_EVENTS. The median is used so one unusually busy unit cannot "
                "carry a building on its own."
            ),
            caveat=(
                "Volume is a count of items, not of volume or mass -- there are no weight "
                "sensors, so a bin full of crisp packets and one full of bottles count alike."
            ),
            evidence=[
                metric("Typical can here", f"{building_median:.0f} items", f"median over {days} days"),
                metric("Typical can campus-wide", f"{campus_median:.0f} items", "median of every can"),
                metric("Pressure ratio", f"{ratio:.1f}x",
                       f"flagged above {CAN_PRESSURE_RATIO}x"),
                metric("Cans in this building", str(len(rows)), "with logged disposals"),
                bars(
                    "Items per can in this building",
                    [{"bucket": code, "value": count,
                      "note": cans[code]["status"] if code in cans else None}
                     for code, count in sorted(rows, key=lambda pair: -pair[1])],
                    "Each bar is one physical can. A single tall bar beside short ones is "
                    "a placement problem; several tall bars is a capacity problem.",
                ),
            ],
        ))

    out.sort(key=lambda r: r["evidence"][2]["value"], reverse=True)
    return out


def retime_collections(context: dict) -> list[dict]:
    """Collection rounds that run at the wrong time of day.

    Grouped into routes, not cans. The first version of this rule emitted one
    card per can and produced twenty-five of them, which is both unreadable
    and wrong about how the work is organised: nobody re-times a single bin,
    they move a round. Cans whose rush ends in the same part of the day are
    therefore collapsed into one recommendation naming the slot and listing
    the units it covers.
    """
    activity = context["activity"]
    cans = {can["can_id"]: can for can in context["fleet"]}

    by_can_hour: dict[int, list[int]] = {}
    for cell in activity["cells"]:
        hours = by_can_hour.setdefault(cell["can_id"], [0] * 24)
        hours[cell["hour_of_day"]] += cell["count"]

    qualifying = []
    for can_id, hours in by_can_hour.items():
        can = cans.get(can_id)
        total = sum(hours)
        if not can or total < MIN_OBSERVATIONS * 2:
            continue

        # The busiest contiguous six hours, wrapping past midnight.
        best_start, best_sum = 0, -1
        for start in range(24):
            window = sum(hours[(start + offset) % 24] for offset in range(6))
            if window > best_sum:
                best_start, best_sum = start, window
        concentration = best_sum / total
        if concentration < PEAK_CONCENTRATION:
            continue

        qualifying.append({
            "can": can,
            "hours": hours,
            "total": total,
            "peak_start": best_start,
            "peak_end": (best_start + 6) % 24,
            "concentration": concentration,
        })

    # Round each can's ideal pickup to the nearest slot a crew could actually
    # be scheduled for. An exact "collect at 7pm for this bin and 8pm for the
    # one beside it" is a rota nobody can run.
    grouped: dict[int, list[dict]] = {}
    for entry in qualifying:
        grouped.setdefault(_nearest_slot((entry["peak_end"] + 1) % 24), []).append(entry)

    out = []
    for slot, entries in grouped.items():
        if len(entries) < MIN_ROUTE_CANS:
            continue
        combined = [0] * 24
        for entry in entries:
            for hour, count in enumerate(entry["hours"]):
                combined[hour] += count
        total = sum(combined)
        in_window = sum(
            count for hour, count in enumerate(combined)
            if _in_window(hour, min(entry["peak_start"] for entry in entries))
        )
        buildings = sorted({entry["can"]["building_name"] for entry in entries})

        out.append(recommendation(
            key=f"route:{slot}",
            kind="operations",
            title=f"Run a {_hour(slot)} collection round for {len(entries)} cans",
            summary=(
                f"{len(entries)} cans across {len(buildings)} building"
                f"{'s' if len(buildings) != 1 else ''} do most of their work before "
                f"{_hour(slot)} and are quiet after it. A round timed to {_hour(slot)} "
                "catches them full once instead of half-full twice."
            ),
            action=(
                f"Add a {_hour(slot)} stop covering {', '.join(buildings[:3])}"
                f"{' and others' if len(buildings) > 3 else ''}, and drop these cans from "
                "the fixed morning sweep."
            ),
            confidence="high" if len(entries) >= MIN_ROUTE_CANS * 2 else "medium",
            window_days=activity["window_days"],
            basis=(
                "Hour-of-day histogram per can over "
                f"{activity['window_days']} days, from the same aggregate the campus "
                "map's usage heatmap draws. Cans qualify when at least "
                f"{PEAK_CONCENTRATION * 100:.0f}% of their disposals fall inside one "
                "six-hour block, and are then grouped by when that block ends."
            ),
            caveat=(
                "Assumes the current round is a morning one. This says when these cans "
                "fill, not how long emptying them takes or whether one crew can reach "
                "them all."
            ),
            evidence=[
                metric("Cans on this round", str(len(entries)),
                       f"across {len(buildings)} building(s)"),
                metric("Suggested pickup", _hour(slot), "just after the rush ends"),
                metric("Share of volume before pickup",
                       f"{in_window / total * 100:.0f}%" if total else "—",
                       f"{in_window:,} of {total:,} disposals"),
                table(
                    "Cans this would cover",
                    ["can", "building", "rush", "in rush", "fill now"],
                    [[entry["can"]["can_code"], entry["can"]["building_name"],
                      f"{_hour(entry['peak_start'])}-{_hour(entry['peak_end'])}",
                      f"{entry['concentration'] * 100:.0f}%",
                      f"{entry['can']['fill_percent']:.0f}%"
                      if entry["can"]["fill_percent"] is not None else "unknown"]
                     for entry in sorted(entries, key=lambda e: -e["concentration"])],
                    "Each can's own rush window and how much of its volume lands inside it.",
                ),
                bars(
                    "Combined disposals by hour",
                    [{"bucket": _hour(hour), "value": count,
                      "note": "pickup" if hour == slot else None}
                     for hour, count in enumerate(combined)],
                    "These cans summed. The suggested pickup sits just past the crest.",
                ),
            ],
        ))

    out.sort(key=lambda r: -len(r["evidence"][3]["rows"]))
    return out


# Slots a crew could plausibly be rostered for, rather than any of 24 hours.
COLLECTION_SLOTS = (7, 11, 15, 19, 22)


def _nearest_slot(hour: int) -> int:
    """The rostered slot closest to an ideal pickup hour, measured around the
    clock so 11pm snaps to the 10pm slot rather than the 7am one."""
    def distance(slot: int) -> int:
        gap = abs(slot - hour)
        return min(gap, 24 - gap)

    return min(COLLECTION_SLOTS, key=distance)


def _hour(hour: int) -> str:
    suffix = "am" if hour < 12 else "pm"
    twelve = hour % 12 or 12
    return f"{twelve}{suffix}"


def _in_window(hour: int, start: int, length: int = 6) -> bool:
    return any((start + offset) % 24 == hour for offset in range(length))


def reduce_food_portions(context: dict) -> list[dict]:
    """Edible food thrown away, by building.

    Only items the catalog marks as edible food count. Peels, cores and spent
    grounds are excluded by that tag and priced at zero: they are evidence
    that food was eaten, and counting them as waste would turn a well-run
    dining hall into a problem on the dashboard.
    """
    days = context["days"]
    rows = context["edible_food"]
    by_building: dict[str, list[dict]] = {}
    for row in rows:
        by_building.setdefault(row["building"] or "unattributed", []).append(row)

    out = []
    for building, items in by_building.items():
        count = sum(item["count"] for item in items)
        cost = sum(item["cost"] for item in items)
        if count < MIN_OBSERVATIONS:
            continue

        annual_cost = _annualise(cost, days)
        worst = max(items, key=lambda item: item["cost"])

        out.append(recommendation(
            key=f"portions:{building}",
            kind="food",
            title=f"Review portion sizes at {building}",
            summary=(
                f"{_plural(count, 'serving')} of edible food were thrown away over {days} days, "
                f"{_money(cost)} at catalog value -- led by {_plain_item(worst['item'])}. "
                f"Food that is served and not eaten is paid for twice: once to buy, "
                f"once to haul."
            ),
            action=(
                f"Trial a smaller default portion of {_plain_item(worst['item']).lower()} "
                f"at {building}, or move it to an on-request item, and re-measure after "
                "two weeks."
            ),
            annual_saving=annual_cost,
            confidence="high" if count >= MIN_OBSERVATIONS * 3 else "medium",
            window_days=days,
            basis=(
                "Disposals matched to catalog products tagged 'edible food'. Consumed "
                "residue -- peels, cores, spent grounds -- is excluded and priced at "
                "zero, because the product it came from was eaten."
            ),
            caveat=(
                "Catalog value is the purchase cost of the item, not the plate price, "
                "and a projection to a year assumes terms run all twelve months."
            ),
            evidence=[
                metric("Edible servings discarded", f"{count:,}", f"over {days} days"),
                metric("Catalog value", _money(cost), "what the food cost to buy"),
                metric("Projected annual value", _money(annual_cost),
                       "straight-line from the window"),
                table(
                    "What is being left",
                    ["item", "servings", "value", "est. mass"],
                    [[item["item"], f"{item['count']:,}", _money(item["cost"]),
                      f"{item['grams'] / 1000:.1f} kg"] for item in
                     sorted(items, key=lambda item: -item["cost"])],
                    "Only items the catalog marks as edible food.",
                ),
            ],
        ))

    out.sort(key=lambda r: r["annual_saving"] or 0, reverse=True)
    return out


def fix_misrouting(context: dict) -> list[dict]:
    """Items landing in a stream their catalog entry disagrees with.

    Both sides are recorded facts, so this needs no reviewer: the stream the
    item went into was logged, and the stream it belongs in is declared by
    its catalog row.
    """
    days = context["days"]
    report = context["misrouted"]
    grouped: dict[tuple, list[dict]] = {}
    for row in report:
        grouped.setdefault((row["logged_as"], row["should_be"]), []).append(row)

    out = []
    for (logged_as, should_be), items in grouped.items():
        count = sum(item["count"] for item in items)
        if count < MIN_OBSERVATIONS:
            continue
        mass_grams = sum(item["grams"] for item in items)

        out.append(recommendation(
            key=f"misroute:{logged_as}->{should_be}",
            kind="sustainability",
            title=f"Fix {should_be} items going into {logged_as}",
            summary=(
                f"{count} items that belong in {should_be} were logged into {logged_as} "
                f"over {days} days -- about {_mass(mass_grams)} sent down the wrong stream."
            ),
            action=(
                f"Re-label the {logged_as} aperture where these items appear, and check "
                f"the sorter's rule for {items[0]['item']} first -- it is the largest single "
                "contributor."
            ),
            confidence="high",
            window_days=days,
            basis=(
                "Compares the stream each item was logged into against the stream its "
                "catalog entry declares. Only items matched to the catalog can be checked, "
                "so this is a floor on the real figure, not a total."
            ),
            caveat=(
                "A misroute may be the depositor's error or the sorter's; this data cannot "
                "tell them apart."
            ),
            evidence=[
                metric("Items misrouted", f"{count:,}", f"{logged_as} instead of {should_be}"),
                metric("Estimated mass", _mass(mass_grams), "catalog reference weights"),
                table(
                    "By item",
                    ["item", "count", "est. mass"],
                    [[item["item"], f"{item['count']:,}", _mass(item["grams"])]
                     for item in sorted(items, key=lambda item: -item["count"])],
                    f"Every catalog product logged into {logged_as} that belongs in {should_be}.",
                ),
            ],
        ))

    out.sort(key=lambda r: r["evidence"][0]["value"], reverse=True)
    return out


def service_backlog(context: dict) -> list[dict]:
    """Cans sitting at or over the service threshold right now.

    Current state rather than a window aggregate, so this one is a worklist
    item more than an insight -- but it belongs beside the others, because
    "empty these today" and "buy fewer cups" compete for the same attention.
    """
    days = context["days"]
    over = [
        can for can in context["fleet"]
        if can["fill_percent"] is not None and can["fill_percent"] >= SERVICE_PRESSURE_PERCENT
    ]
    if len(over) < 2:
        return []

    by_building: dict[str, list[dict]] = {}
    for can in over:
        by_building.setdefault(can["building_name"], []).append(can)
    worst_building = max(by_building.items(), key=lambda pair: len(pair[1]))

    return [recommendation(
        key="service:backlog",
        kind="operations",
        title=f"{len(over)} cans are at or over the service threshold",
        summary=(
            f"{len(over)} of the fleet are at {SERVICE_PRESSURE_PERCENT:.0f}% or more"
            + (
                f", {len(worst_building[1])} of them in {worst_building[0]}. Several in one "
                "building points at a round that is missing a stop rather than a fleet "
                "that is undersized."
                if len(worst_building[1]) > 1
                else f", spread across {_plural(len(by_building), 'building')} with no more "
                "than one each. That is a pacing problem across the whole route, not a "
                "building being skipped."
            )
        ),
        action=(
            f"Empty {_plural(len(worst_building[1]), 'can')} in {worst_building[0]} first"
            + (
                ", then check whether that building is on the current collection route at all."
                if len(worst_building[1]) > 1
                else ", then review the interval between rounds rather than the route itself."
            )
        ),
        confidence="high",
        window_days=days,
        basis=(
            "The latest reading for every active can, with fill resolved by fleet.py -- "
            "counted from disposals for a reporting unit, carried from a seeded reading "
            "for a simulated one."
        ),
        caveat=(
            "Simulated cans carry a seeded fill rather than an observed one; the "
            "fill source column says which is which."
        ),
        evidence=[
            metric("Cans over threshold", str(len(over)),
                   f"at or above {SERVICE_PRESSURE_PERCENT:.0f}%"),
            metric("Worst building", worst_building[0],
                   f"{len(worst_building[1])} of {len(over)}"),
            table(
                "Cans needing service",
                ["can", "building", "fill", "source", "items since emptied"],
                [[can["can_code"], can["building_name"], f"{can['fill_percent']:.0f}%",
                  can["fill_source"], str(can["events_since_emptied"])]
                 for can in sorted(over, key=lambda can: -can["fill_percent"])],
                "Live fleet state, not a window aggregate.",
            ),
        ],
    )]


RULES = (
    switch_to_reusable,
    reduce_food_portions,
    add_or_relocate_cans,
    retime_collections,
    fix_misrouting,
    service_backlog,
)

KIND_ORDER = {"procurement": 0, "food": 1, "operations": 2, "placement": 3, "sustainability": 4}


def generate(days: int = 30, limit: int | None = None) -> dict:
    """Every rule, ranked.

    Ranking is projected annual saving first, because that is the question
    the money rules answer and the one most likely to be acted on; rules with
    no money attached fall back to their kind's order rather than being
    pushed to the bottom, since "two cans are overflowing" outranks "save $40
    a year on straws" on any given morning.
    """
    context = build_context(days)
    produced: list[dict] = []
    failures: list[str] = []
    for rule in RULES:
        try:
            produced.extend(rule(context))
        except Exception as exc:  # one broken rule must not empty the page
            failures.append(f"{rule.__name__}: {type(exc).__name__}")

    produced.sort(
        key=lambda item: (
            -(item["annual_saving"] or 0),
            KIND_ORDER.get(item["kind"], 9),
            item["title"],
        )
    )
    if limit:
        produced = produced[:limit]

    total_saving = sum(item["annual_saving"] or 0 for item in produced)
    return {
        "window_days": days,
        "generated": len(produced),
        "recommendations": produced,
        "projected_annual_saving": round(total_saving, 2),
        "rules_run": len(RULES),
        "rules_failed": failures,
        "assumptions": {
            "wash_cost_per_use": WASH_COST_PER_USE,
            "min_observations": MIN_OBSERVATIONS,
            "can_pressure_ratio": CAN_PRESSURE_RATIO,
            "peak_concentration": PEAK_CONCENTRATION,
        },
        "note": (
            "Savings are projections from the window shown, not booked figures. Every "
            "card carries the observations it was derived from; open one before acting "
            "on it."
        ),
    }
