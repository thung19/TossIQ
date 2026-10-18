"""Seeds hazardous disposal events, and backfills classification onto any
hazard the live pipeline logged.

Two jobs:

  * Classify. Every flagged event gets a HAZARD_CLASS and HAZARD_SEVERITY
    from hazards.classify, stored rather than recomputed, so the hazards
    page can group and filter in SQL. Runs over anything unclassified,
    including events the vision model flagged after the last run.

  * Seed. The demo database had HAZARD_FLAG set on exactly zero of its 1,090
    events, because the only writer is the advanced vision path and nobody
    has waved a vape at the camera. A hazards page with nothing on it
    demonstrates nothing, so a plausible set is seeded here.

Seeded hazards are marked the same way seed_campus marks its synthetic
disposals -- no IMAGE_KEY, and a LOCATION equal to the can's own code -- so
they stay distinguishable from anything the pipeline actually saw.

!! THESE ARE INVENTED INCIDENTS !!
Nobody threw a syringe into Rand Hall. The placement is chosen to be
plausible -- vapes near residences and the rec centre, chemicals near the
science precinct, sharps near the health-adjacent buildings -- so the page
shows the patterns it is built to surface.

Run from the repository root, after schema/apply.py:
    python seed_hazards.py

    --reseed       add another round of incidents even though some exist.
    --reclassify   recompute the class on every flagged event, for when the
                   taxonomy has been corrected.
"""

import random
import sys
from datetime import datetime, timedelta

import db
import hazards

RANDOM_SEED = 20261019

# How many incidents to seed in total, spread across the last two weeks.
INCIDENT_COUNT = 34
WINDOW_DAYS = 14

# (detected_object, hazard_reason, buildings it plausibly turns up in, weight)
#
# The building lists are the whole point of the seed: a hazards page exists
# to show WHERE, and hazards distributed uniformly would show nothing. Vapes
# cluster in residences and the rec centre, solvents in the science precinct,
# batteries everywhere because every building has a drawer of them.
INCIDENTS = [
    ("disposable vape", "Sealed lithium cell visible through cracked casing",
     ["VU-BRANSCOMB", "VU-HIGHLAND", "VU-REC", "VU-COMMONS", "VU-SLC"], 7),
    ("vape pen", "Nicotine pod attached to a rechargeable body",
     ["VU-BRANSCOMB", "VU-HIGHLAND", "VU-REC"], 4),
    ("AA battery", "Visible battery compartment, alkaline cell",
     ["VU-LIBRARY", "VU-KIRKLAND", "VU-BUTTRICK", "VU-ALUMNI", "VU-STEVENSON"], 5),
    ("9V battery", "Exposed terminals on a 9V alkaline cell",
     ["VU-STEVENSON", "VU-FEATHERINGILL", "VU-WONDRY"], 3),
    ("power bank", "Swollen lithium-ion pack, casing split",
     ["VU-LIBRARY", "VU-WONDRY", "VU-FEATHERINGILL"], 3),
    ("laptop battery", "Lithium-ion battery removed from a laptop chassis",
     ["VU-FEATHERINGILL", "VU-WONDRY"], 2),
    ("aerosol can", "Pressurised can with a flammable symbol on the label",
     ["VU-REC", "VU-BRANSCOMB", "VU-HIGHLAND"], 3),
    ("spray paint can", "Part-full aerosol, hazard diamond visible",
     ["VU-WONDRY", "VU-FEATHERINGILL"], 2),
    ("reagent bottle", "Chemical hazard symbol and a lab label",
     ["VU-STEVENSON", "VU-FEATHERINGILL"], 3),
    ("solvent bottle", "Corrosive warning symbol on a part-full bottle",
     ["VU-STEVENSON"], 2),
    ("syringe", "Exposed needle, no sharps cap",
     ["VU-REC", "VU-SLC"], 2),
    ("lancet", "Single-use lancet with the point exposed",
     ["VU-REC"], 1),
    ("fluorescent tube", "Intact mercury-containing tube",
     ["VU-STEVENSON", "VU-BUTTRICK"], 2),
    ("pill bottle", "Prescription label with tablets still inside",
     ["VU-SLC", "VU-BRANSCOMB", "VU-HIGHLAND"], 3),
    ("phone charger", "Mains adapter with a frayed cable",
     ["VU-LIBRARY", "VU-ALUMNI", "VU-COMMONS"], 3),
    ("earbuds", "Sealed battery in each bud",
     ["VU-LIBRARY", "VU-REC"], 2),
    # Deliberately unmatched: the model flags something it cannot name, and
    # the page has to cope with that rather than pretending every hazard
    # classifies.
    ("unidentified container", "Unlabelled bottle with a corroded cap; contents unknown",
     ["VU-STEVENSON", "VU-WONDRY"], 2),
]

# Hour-of-day weights. Hazards arrive on the same daily rhythm as everything
# else, with a late-evening skew for vapes.
HAZARD_HOUR_WEIGHTS = [
    2, 2, 1, 0, 0, 1, 2, 5, 9, 11, 10, 10, 12, 11, 10, 9, 11, 13, 15, 14, 12, 9, 6, 4
]

_HAZARD_INSERT = """
INSERT INTO waste_events
    (detected_object, material, category, location, confidence, created_at, bin_id,
     hazard_flag, hazard_reason, hazard_class, hazard_severity, hazard_status)
VALUES
    (:detected_object, :material, :category, :location, :confidence, :created_at, :bin_id,
     1, :hazard_reason, :hazard_class, :hazard_severity, 'open')
"""


def classify_existing() -> int:
    """Backfills HAZARD_CLASS / HAZARD_SEVERITY onto flagged events that have
    none, including anything the live pipeline logged since the last run."""
    pending = db.list_unclassified_hazards()
    rows = []
    for event_id, detected_object, hazard_reason in pending:
        verdict = hazards.classify(detected_object, hazard_reason)
        rows.append({
            "event_id": event_id,
            "hazard_class": verdict["hazard_class"],
            "hazard_severity": verdict["severity"],
        })
    return db.set_hazard_classification(rows)


def seed_incidents() -> int:
    """Inserts the demo incident set, placed in plausible buildings."""
    rng = random.Random(RANDOM_SEED)
    now = datetime.now()

    cans_by_building: dict[str, list[dict]] = {}
    for can in db.list_can_rows():
        prefix = can["can_code"].rsplit("-", 1)[0]
        cans_by_building.setdefault(prefix, []).append(can)

    population = [entry for entry in INCIDENTS for _ in range(entry[3])]
    rows = []
    for _ in range(INCIDENT_COUNT):
        detected_object, reason, buildings, _weight = rng.choice(population)
        candidates = [
            can for prefix in buildings for can in cans_by_building.get(prefix, [])
        ]
        if not candidates:
            continue
        can = rng.choice(candidates)
        verdict = hazards.classify(detected_object, reason)

        days_back = rng.uniform(0, WINDOW_DAYS)
        hour = rng.choices(range(24), weights=HAZARD_HOUR_WEIGHTS, k=1)[0]
        when = (now - timedelta(days=days_back)).replace(
            hour=hour, minute=rng.randrange(60), second=rng.randrange(60), microsecond=0
        )
        if when > now:
            when -= timedelta(days=1)

        rows.append({
            "detected_object": detected_object,
            "material": "hazardous",
            # A hazard has no correct stream among the three the sorter
            # offers, and filing it as landfill would be the system telling
            # itself the item was handled.
            "category": None,
            "location": can["can_code"],
            "confidence": rng.randrange(68, 97),
            "created_at": when,
            "bin_id": can["can_id"],
            "hazard_reason": reason,
            "hazard_class": verdict["hazard_class"],
            "hazard_severity": verdict["severity"],
        })

    if not rows:
        return 0
    with db.get_connection() as conn, conn.cursor() as cursor:
        cursor.executemany(_HAZARD_INSERT, rows)
        conn.commit()
    return len(rows)


def acknowledge_some() -> int:
    """Acknowledges a minority of the older incidents.

    A page where everything is outstanding looks like nobody is using it;
    one where everything is cleared has nothing to show. The older half gets
    a partial sweep, which is what a real worklist looks like.
    """
    rng = random.Random(RANDOM_SEED + 1)
    reviewers = [
        "ehs@vanderbilt.edu", "facilities-ops@vanderbilt.edu", "m.okafor@vanderbilt.edu",
    ]
    outstanding = db.list_hazard_disposals(days=WINDOW_DAYS, outstanding_only=True, limit=500)
    # Only the back half of the window: recent ones stay open so the page
    # opens on actual work.
    older = [row for row in outstanding if row["created_at"] < (
        datetime.now() - timedelta(days=WINDOW_DAYS / 2)
    ).strftime("%Y-%m-%d %H:%M:%S")]

    done = 0
    for row in older:
        if rng.random() > 0.6:
            continue
        if db.acknowledge_hazard(
            row["event_id"],
            rng.choice(reviewers),
            "Collected and routed to the hazardous waste contractor.",
        ):
            done += 1
    return done


def reclassify_all() -> int:
    """Recomputes the class on every flagged event.

    Needed when the taxonomy changes, which it will: the keyword table is
    the thing that gets corrected when a hazard turns up filed as the wrong
    kind. Separate from the backfill because it overwrites rather than
    filling gaps.
    """
    rows = []
    for row in db.list_hazard_disposals(days=3650, limit=5000):
        verdict = hazards.classify(row["detected_object"], row["hazard_reason"])
        rows.append({
            "event_id": row["event_id"],
            "hazard_class": verdict["hazard_class"],
            "hazard_severity": verdict["severity"],
        })
    return db.set_hazard_classification(rows)


def main() -> None:
    reseed = "--reseed" in sys.argv
    reclassify = "--reclassify" in sys.argv

    print("Seeding hazardous disposals.")
    print("  INCIDENTS ARE INVENTED -- see module docstring.")

    if reclassify:
        print(f"  reclassified:    {reclassify_all()} flagged event(s) against the taxonomy")
    else:
        print(f"  classified:      {classify_existing()} newly flagged event(s)")

    existing = len(db.list_hazard_disposals(days=WINDOW_DAYS, limit=500))
    if existing and not reseed:
        print(f"  incidents:       {existing} already present (pass --reseed to add more)")
    else:
        print(f"  incidents:       {seed_incidents()} new")
        print(f"  acknowledged:    {acknowledge_some()} of the older ones")

    print("Done.")


if __name__ == "__main__":
    main()
