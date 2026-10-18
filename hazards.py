"""Hazardous-disposal classification, alerting and handling guidance.

WASTE_EVENTS has carried HAZARD_FLAG and HAZARD_REASON since the advanced
vision path was written: the model raises them when it sees a battery
compartment, a warning symbol or sharps. That was enough to say "something
was wrong with this item" and nothing more -- a flagged lithium cell and a
flagged pill bottle were the same row to every query in the system, with no
way to tell a fire risk from a litter problem.

This module is the missing half. It gives each flagged item a CLASS, a
SEVERITY and the handling the class actually requires, and it surfaces the
pattern that matters more than any single event: the same hazard turning up
in the same place over and over, which is a signage or collection problem
rather than one careless person.

Classification is keyword matching over the model's own label and reason
text, not a second model. Two reasons. The vision model has already done the
hard part -- deciding something is hazardous at all -- and what remains is
mapping its words onto a fixed taxonomy that safety procedure is written
against. And a keyword table is auditable: when a vape is routed to
CRITICAL, an operator can read the line that did it.

The severity ladder is about response time, not about how unpleasant
something is:

  critical  can start a fire in a compacted load, or injure a handler who
            reaches in. Lithium cells, vapes, sharps, mercury.
  high      harms the handler or the waste stream, but will not combust in
            the truck. Alkaline cells, aerosols, chemicals, pharmaceuticals.
  medium    must not be landfilled and has a legal route elsewhere.
            Electronics.
"""

from datetime import datetime

import db

# (class, severity, display name, keywords, handling instruction)
#
# Keywords are matched against the detected label and the model's hazard
# reason, lowercased, as substrings. Ordered most specific first: "lithium
# battery" has to be tested before "battery", or every lithium cell is
# filed as an alkaline one.
HAZARD_TAXONOMY = [
    (
        "vape", "critical", "Vape / e-cigarette",
        ("vape", "e-cigarette", "ecigarette", "e-cig", "juul", "nicotine pod", "vape pen"),
        "Contains a sealed lithium cell and nicotine residue. Do not compact. "
        "Bag separately and route to the e-waste contractor; most councils will "
        "not take these in any kerbside stream.",
    ),
    (
        "lithium_battery", "critical", "Lithium battery",
        ("lithium", "li-ion", "lion battery", "power bank", "laptop battery",
         "phone battery", "rechargeable battery", "18650"),
        "Fire risk if punctured or crushed. Do not place in any compacting bin. "
        "Tape the terminals, isolate in a non-conductive container and call the "
        "battery collection contractor.",
    ),
    (
        "sharps", "critical", "Sharps",
        ("needle", "syringe", "lancet", "scalpel", "razor blade", "broken glass vial",
         "sharps"),
        "Injury and infection risk to anyone handling the bag. Do not reach into "
        "the bin. Retrieve with tongs into a rigid sharps container and log the "
        "bin for a glove-and-tongs inspection.",
    ),
    (
        "mercury", "critical", "Mercury-containing",
        ("fluorescent", "cfl", "mercury", "thermometer", "mercury lamp"),
        "Releases mercury vapour if broken. Do not sweep or vacuum if already "
        "broken; ventilate the area and call Environmental Health and Safety.",
    ),
    (
        "aerosol", "high", "Aerosol",
        ("aerosol", "spray can", "spray paint", "deodorant can", "air freshener"),
        "Pressurised and often flammable. Keep out of compacting loads; empty "
        "cans go to the metal stream, part-full ones to hazardous collection.",
    ),
    (
        # Tested after aerosol, and deliberately without the bare word
        # "pressurised": that is an adjective the model uses in the reason
        # text for any can under pressure, and matching on it filed every
        # deodorant aerosol as a propane cylinder. Only the specific vessels
        # count here.
        "pressurised", "high", "Pressurised cylinder",
        ("propane", "butane", "gas cylinder", "lpg", "co2 cartridge",
         "pressurized cylinder", "pressurised cylinder", "compressed gas"),
        "Explodes under compaction or heat. Remove before the bin is collected "
        "and route to the gas supplier's return scheme.",
    ),
    (
        "chemical", "high", "Chemical / solvent",
        ("solvent", "bleach", "acid", "corrosive", "reagent", "paint can", "paint tin",
         "chemical", "pesticide", "drain cleaner", "hazard warning symbol",
         "hazard symbol"),
        "May react with other waste in the bag. Do not mix. Seal, label with what "
        "it is if known, and route to the lab chemical waste contractor.",
    ),
    (
        "pharmaceutical", "high", "Pharmaceutical",
        ("pill bottle", "medication", "blister pack", "prescription", "pharmaceutical",
         "tablet strip", "inhaler"),
        "Must not enter landfill or water. Route to the pharmacy take-back bin; "
        "controlled substances need a witnessed disposal.",
    ),
    (
        "alkaline_battery", "high", "Alkaline battery",
        ("battery", "batteries", "aa cell", "aaa cell", "9v", "button cell",
         "coin cell", "battery compartment"),
        "Leaks potassium hydroxide as it degrades and is banned from landfill in "
        "most states. Collect in the battery tube at the building entrance.",
    ),
    (
        "e_waste", "medium", "Electronic waste",
        ("charger", "cable", "circuit board", "headphones", "earbuds", "phone",
         "laptop", "electronic", "adapter", "mouse", "keyboard"),
        "Has a legal recycling route and often recoverable value. Route to the "
        "IT asset disposal bin rather than any waste stream.",
    ),
]

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "unclassified": 3}

# How quickly each severity is meant to be dealt with. Used to decide when an
# acknowledged-by-nobody hazard becomes an escalation rather than an item on
# a list.
RESPONSE_HOURS = {"critical": 4, "high": 24, "medium": 72, "unclassified": 24}

# Same class, same building, this many times inside the window, and the
# problem is the place rather than the person: somebody needs a collection
# point or a sign, not a telling-off.
RECURRENCE_THRESHOLD = 3

UNCLASSIFIED = {
    "hazard_class": "unclassified",
    "severity": "unclassified",
    "display_name": "Unclassified hazard",
    "handling": (
        "The model flagged this as hazardous but its description matched no known "
        "class. Inspect before handling and, if it is a recognisable hazard, add "
        "its wording to the taxonomy so the next one classifies itself."
    ),
}


def classify(detected_object: str | None, hazard_reason: str | None) -> dict:
    """Maps a flagged item onto the taxonomy.

    Matches against the label and the model's reason together, because the
    two carry different halves of the evidence: the label says "disposable
    vape" while the reason says "visible battery compartment", and either
    alone would miss cases the other catches.

    Returns UNCLASSIFIED rather than guessing when nothing matches. An
    unrecognised hazard that announces itself as unrecognised is safe; one
    quietly filed as an alkaline battery is not.
    """
    haystack = " ".join(part.lower() for part in (detected_object, hazard_reason) if part)
    if not haystack:
        return dict(UNCLASSIFIED)

    for hazard_class, severity, display_name, keywords, handling in HAZARD_TAXONOMY:
        if any(keyword in haystack for keyword in keywords):
            return {
                "hazard_class": hazard_class,
                "severity": severity,
                "display_name": display_name,
                "handling": handling,
            }
    return dict(UNCLASSIFIED)


def display_name(hazard_class: str | None) -> str:
    for entry in HAZARD_TAXONOMY:
        if entry[0] == hazard_class:
            return entry[2]
    return UNCLASSIFIED["display_name"]


def handling_for(hazard_class: str | None) -> str:
    for entry in HAZARD_TAXONOMY:
        if entry[0] == hazard_class:
            return entry[4]
    return UNCLASSIFIED["handling"]


def severity_for(hazard_class: str | None) -> str:
    for entry in HAZARD_TAXONOMY:
        if entry[0] == hazard_class:
            return entry[1]
    return "unclassified"


# ---------------------------------------------------------------------------
# Alerting
# ---------------------------------------------------------------------------

def _hours_since(timestamp: str | None, now: datetime) -> float | None:
    if not timestamp:
        return None
    return (now - datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600.0


def summary(days: int = 30, now: datetime | None = None) -> dict:
    """What is outstanding, where it is concentrating, and what is overdue.

    Two kinds of alert, because they call for different responses:

      overdue     a specific hazard nobody has acknowledged inside the
                  response window its severity demands. Somebody needs to
                  go and deal with that item.
      recurring   the same class turning up in the same building repeatedly.
                  Dealing with each one individually will not stop the next;
                  that building needs a collection point or a sign.
    """
    now = now or datetime.now()

    outstanding = db.list_hazard_disposals(days=days, outstanding_only=True, limit=500)
    by_class = db.hazard_class_counts(days=days)
    by_location = db.hazard_location_counts(days=days)

    overdue = []
    for row in outstanding:
        severity = row.get("hazard_severity") or "unclassified"
        age = _hours_since(row.get("created_at"), now)
        limit = RESPONSE_HOURS.get(severity, 24)
        if age is not None and age > limit:
            overdue.append({
                "event_id": row["event_id"],
                "detected_object": row["detected_object"],
                "hazard_class": row.get("hazard_class"),
                "display_name": display_name(row.get("hazard_class")),
                "severity": severity,
                "building_name": row.get("building_name"),
                "can_code": row.get("can_code"),
                "created_at": row.get("created_at"),
                "hours_open": round(age, 1),
                "response_hours": limit,
                "hours_overdue": round(age - limit, 1),
            })
    overdue.sort(key=lambda item: (SEVERITY_ORDER.get(item["severity"], 9),
                                   -item["hours_overdue"]))

    recurring = [
        {
            **row,
            "display_name": display_name(row["hazard_class"]),
            "handling": handling_for(row["hazard_class"]),
        }
        for row in by_location
        if row["count"] >= RECURRENCE_THRESHOLD and row["building_name"] != "unattributed"
    ]
    recurring.sort(key=lambda row: (SEVERITY_ORDER.get(row["severity"], 9), -row["count"]))

    severity_totals: dict[str, dict] = {}
    for row in by_class:
        entry = severity_totals.setdefault(
            row["severity"], {"severity": row["severity"], "count": 0, "outstanding": 0}
        )
        entry["count"] += row["count"]
        entry["outstanding"] += row["outstanding"]

    total = sum(row["count"] for row in by_class)
    return {
        "window_days": days,
        "total": total,
        "outstanding": sum(row["outstanding"] for row in by_class),
        "by_severity": sorted(
            severity_totals.values(),
            key=lambda row: SEVERITY_ORDER.get(row["severity"], 9),
        ),
        "by_class": [
            {**row, "display_name": display_name(row["hazard_class"]),
             "handling": handling_for(row["hazard_class"])}
            for row in by_class
        ],
        "by_location": by_location,
        "overdue": overdue,
        "recurring": recurring,
        "trend": db.hazard_trend(days=days),
        "response_hours": dict(RESPONSE_HOURS),
        "recurrence_threshold": RECURRENCE_THRESHOLD,
        "note": (
            "A hazard is flagged by the vision model and classified by keyword against "
            "a fixed taxonomy. An item it cannot place is reported as unclassified "
            "rather than guessed at. Nothing here is a measurement of quantity -- it is "
            "a count of items seen."
        ),
    }
