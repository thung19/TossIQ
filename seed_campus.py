"""Seeds the mock Vanderbilt can fleet: models, buildings, cans, telemetry,
service history, and synthetic disposal events.

Idempotent and re-runnable. Inventory rows (CAN_MODELS / BUILDINGS / CANS) are
matched on their natural codes and inserted only when absent. The append-only
tables (CAN_READINGS / SERVICE_EVENTS / WASTE_EVENTS) are seeded per can only
when that can has no rows yet, so a second run adds nothing rather than
stacking a second telemetry tail.

Everything here is mock except the two cans marked IS_SIMULATED = 0, which
stand for the hardware TossIQ actually runs: those two take their fill from
counted disposal events, not from a seeded number. That flag is the line
between what the system observed and what was invented for the demo.

!! COORDINATES ARE APPROXIMATE !!
The per-building latitude/longitude below were placed by hand around a campus
centre of roughly 36.145 N, -86.803 W. They put each building in the right
part of campus and nothing more; they are not surveyed positions and must be
refined from a real source (the university's GIS data or an OSM extract)
before this map is shown as authoritative.

Run from the repository root, after schema/apply.py:
    python seed_campus.py

Two opt-in flags exist for refreshing a database seeded some time ago:

    --refresh-readings   appends one current telemetry reading per can, so a
                         fleet whose tail has aged past the staleness limit
                         stops reading as entirely offline.
    --reshape-times      rewrites CREATED_AT on synthetic disposals an earlier
                         run wrote with uniformly random timestamps, so the
                         usage heatmap shows the daily rhythm described in
                         HOUR_WEIGHTS_BY_PROFILE.

--reshape-times is the one destructive thing in here, which is why it is
opt-in; it never touches events the live pipeline logged.
"""

import random
import sys
from datetime import datetime, timedelta

import db

RANDOM_SEED = 20261017  # fixed so the demo fleet's health mix is reproducible

CAMPUS_CENTRE = (36.145, -86.803)

# Hardware SKUs. CAPACITY_ITEMS is what derived fill divides by, so the
# 240 L high-traffic unit tolerates more disposals before it needs emptying.
CAN_MODELS = [
    {
        "model_code": "TQ-S-120",
        "display_name": "TossIQ Standard 120L (3-stream)",
        "capacity_liters": 120.0,
        "capacity_items": 320,
        "height_cm": 101.5,
        "stream_count": 3,
        "has_camera": 1,
        "has_actuator": 1,
        "firmware_version": "2.4.1",
        "released_on": datetime(2026, 3, 2),
    },
    {
        "model_code": "TQ-H-240",
        "display_name": "TossIQ High-Traffic 240L (3-stream)",
        "capacity_liters": 240.0,
        "capacity_items": 640,
        "height_cm": 118.0,
        "stream_count": 3,
        "has_camera": 1,
        "has_actuator": 1,
        "firmware_version": "2.4.1",
        "released_on": datetime(2026, 6, 15),
    },
    {
        # Older unit: it sees items but cannot sort them, so its stream
        # assignment is advisory only. Kept in the fleet so hardware-version
        # filtering has a genuinely different capability to show.
        "model_code": "TQ-L-90",
        "display_name": "TossIQ Legacy 90L (2-stream, no actuator)",
        "capacity_liters": 90.0,
        "capacity_items": 220,
        "height_cm": 92.0,
        "stream_count": 2,
        "has_camera": 1,
        "has_actuator": 0,
        "firmware_version": "1.8.7",
        "released_on": datetime(2025, 8, 20),
    },
]

# (building_code, name, campus_area, latitude, longitude, waste profile)
# The profile weights the synthetic category mix so the map is not uniform
# noise: dining buildings skew compost and landfill, the library skews
# recycling, labs and admin sit in between.
BUILDINGS = [
    ("VU-RAND", "Rand Hall", "Main Campus", 36.14650, -86.80430, "dining"),
    ("VU-SARRATT", "Sarratt Student Center", "Main Campus", 36.14690, -86.80490, "dining"),
    ("VU-COMMONS", "Commons Center", "The Commons", 36.14230, -86.80110, "dining"),
    ("VU-LIBRARY", "Central Library", "Main Campus", 36.14510, -86.80290, "library"),
    ("VU-STEVENSON", "Stevenson Center", "Science Precinct", 36.14450, -86.80600, "lab"),
    ("VU-FEATHERINGILL", "Featheringill Hall", "Engineering", 36.14440, -86.80770, "lab"),
    ("VU-KIRKLAND", "Kirkland Hall", "Main Campus", 36.14780, -86.80280, "admin"),
    ("VU-SLC", "Student Life Center", "Main Campus", 36.14140, -86.80390, "dining"),
    ("VU-BUTTRICK", "Buttrick Hall", "Main Campus", 36.14710, -86.80190, "classroom"),
    ("VU-ALUMNI", "Alumni Hall", "Main Campus", 36.14600, -86.80180, "classroom"),
    ("VU-BRANSCOMB", "Branscomb Quad", "Residential", 36.14390, -86.80360, "residential"),
    ("VU-HIGHLAND", "Highland Quad", "Residential", 36.14960, -86.80700, "residential"),
    ("VU-REC", "Student Recreation Center", "Main Campus", 36.14310, -86.80680, "recreation"),
    ("VU-WONDRY", "The Wond'ry", "Engineering", 36.14520, -86.80830, "lab"),
    ("VU-DIVINITY", "Divinity School", "Main Campus", 36.14840, -86.80530, "classroom"),
]

# Category weights per waste profile, as (category, weight) pairs.
PROFILE_CATEGORY_WEIGHTS = {
    "dining": [("compost", 5), ("landfill", 3), ("recycling", 2)],
    "library": [("recycling", 6), ("landfill", 2), ("compost", 1)],
    "lab": [("recycling", 4), ("landfill", 4), ("compost", 1)],
    "admin": [("recycling", 5), ("landfill", 3), ("compost", 1)],
    "classroom": [("recycling", 4), ("landfill", 3), ("compost", 2)],
    "residential": [("landfill", 4), ("recycling", 3), ("compost", 2)],
    "recreation": [("landfill", 4), ("recycling", 4), ("compost", 1)],
}

# Plausible detected_object values per category, so per-can "top items" reads
# like a real dining hall or library rather than a placeholder list.
OBJECTS_BY_CATEGORY = {
    "compost": [
        "paper food boat", "napkin", "banana peel", "coffee grounds",
        "compostable fork", "pizza crust", "apple core", "paper cup sleeve",
    ],
    "recycling": [
        "aluminum can", "plastic water bottle", "cardboard sleeve",
        "printer paper", "glass bottle", "plastic clamshell", "notebook page",
    ],
    "landfill": [
        "chip bag", "plastic straw", "coffee lid", "candy wrapper",
        "styrofoam cup", "disposable glove", "plastic cutlery",
    ],
}

MATERIAL_BY_CATEGORY = {
    "compost": "organic",
    "recycling": "aluminum",
    "landfill": "mixed plastic",
}

# How many cans each building gets, 1-5, and which model each gets. Written
# out rather than randomised so the fleet layout is reviewable and stable.
# (building_code, [model_code per can])
CAN_LAYOUT = [
    ("VU-RAND", ["TQ-H-240", "TQ-H-240", "TQ-S-120", "TQ-S-120", "TQ-L-90"]),
    ("VU-SARRATT", ["TQ-H-240", "TQ-S-120", "TQ-S-120", "TQ-L-90"]),
    ("VU-COMMONS", ["TQ-H-240", "TQ-S-120", "TQ-S-120", "TQ-L-90"]),
    ("VU-LIBRARY", ["TQ-S-120", "TQ-S-120", "TQ-S-120", "TQ-L-90"]),
    ("VU-STEVENSON", ["TQ-S-120", "TQ-S-120", "TQ-L-90"]),
    ("VU-FEATHERINGILL", ["TQ-S-120", "TQ-L-90"]),
    ("VU-KIRKLAND", ["TQ-S-120", "TQ-L-90"]),
    ("VU-SLC", ["TQ-H-240", "TQ-S-120", "TQ-S-120"]),
    ("VU-BUTTRICK", ["TQ-S-120", "TQ-L-90"]),
    ("VU-ALUMNI", ["TQ-S-120", "TQ-S-120", "TQ-L-90"]),
    ("VU-BRANSCOMB", ["TQ-H-240", "TQ-S-120", "TQ-S-120", "TQ-L-90"]),
    ("VU-HIGHLAND", ["TQ-S-120", "TQ-S-120", "TQ-L-90"]),
    ("VU-REC", ["TQ-H-240", "TQ-S-120"]),
    ("VU-WONDRY", ["TQ-S-120", "TQ-S-120"]),
    ("VU-DIVINITY", ["TQ-S-120", "TQ-L-90"]),
]

PLACEMENT_NOTES = [
    "north entrance", "south entrance", "main lobby", "by the elevators",
    "servery exit", "outside the loading door", "central atrium", "stairwell landing",
]

# Two cans stand for real reporting hardware rather than the mock fleet, and
# are the targets the legacy free-text LOCATION strings are attributed to.
# Their fill is counted from disposal events, never seeded.
REAL_CAN_CODES = {"VU-RAND-01", "VU-LIBRARY-01"}

# Explicit, reviewable attribution of pre-existing free-text LOCATION values to
# a seeded can. Written out rather than fuzzy-matched: only these two strings
# clearly correspond to a physical unit. 'FIRSTMATE-TEST', 'SKU Verification'
# and 'Loading Dock B' are test-harness captures with no can behind them and
# are deliberately left with BIN_ID NULL.
LEGACY_LOCATION_TO_CAN_CODE = {
    "live-webcam": "VU-LIBRARY-01",
    "Vanderbilt Dining Hall": "VU-RAND-01",
}

# The demo health mix, keyed by can_code so it is reviewable rather than
# emergent from a random draw. Every other can is seeded healthy.
# fill is the seeded fill_percent for a simulated can; the hardware flags and
# fault codes apply to both simulated and real cans, since a real unit reports
# its own hardware health even when its fill is counted elsewhere.
HEALTH_OVERRIDES = {
    # Over the 80% service threshold -- the emptying worklist.
    "VU-RAND-02": {"fill": 96.0},
    "VU-SARRATT-01": {"fill": 91.5},
    "VU-COMMONS-01": {"fill": 88.0},
    "VU-SLC-01": {"fill": 84.5},
    "VU-BRANSCOMB-01": {"fill": 93.0},
    "VU-REC-01": {"fill": 81.0},
    # Camera down: the unit still sorts on its last known rules but logs nothing.
    "VU-LIBRARY-02": {"camera_ok": 0, "fault_code": "CAM_TIMEOUT",
                      "fault_detail": "Camera did not return a frame for 40 consecutive cycles"},
    "VU-STEVENSON-01": {"camera_ok": 0, "fault_code": "CAM_TIMEOUT",
                        "fault_detail": "Camera did not return a frame for 12 consecutive cycles"},
    "VU-HIGHLAND-02": {"camera_ok": 0, "fault_code": "CAM_LENS",
                       "fault_detail": "Lens obstruction detected; frames uniformly dark"},
    # Dead actuator: items are identified but fall through unsorted.
    "VU-BUTTRICK-01": {"actuator_ok": 0, "fault_code": "ACT_STALL",
                       "fault_detail": "Diverter flap stalled mid-travel"},
    # Offline, exercising both routes into that status: one unit that reports
    # its own uplink as down, and one that has simply stopped reporting.
    "VU-FEATHERINGILL-02": {"connectivity_ok": 0},
    "VU-DIVINITY-02": {"stale_hours": 31},
}

# Non-active cans, so LIFECYCLE_STATUS carries real variety. These are excluded
# from the map payload and from fleet health by db.list_can_rows.
LIFECYCLE_OVERRIDES = {
    "VU-WONDRY-02": "staging",
    "VU-KIRKLAND-02": "removed",
}

# Mirrors fleet.SERVICE_THRESHOLD_PERCENT's default. Kept as its own constant
# rather than imported, because the seed describes the fleet it wants to
# produce; it must not silently reshape itself when the runtime threshold is
# retuned via FLEET_SERVICE_THRESHOLD_PERCENT.
SERVICE_THRESHOLD_FILL = 80.0

_SYNTHETIC_EVENT_INSERT = """
INSERT INTO waste_events
    (detected_object, material, category, location, confidence, created_at, bin_id, product_id)
VALUES
    (:detected_object, :material, :category, :location, :confidence, :created_at, :bin_id, :product_id)
"""

READING_TAIL_DAYS = 7
READINGS_PER_DAY = 4

# How far back synthetic disposals are spread, and how many each can gets.
# Two weeks so every weekday is sampled twice, which is the minimum for the
# usage heatmap's day-of-week rows to be a pattern rather than a single day's
# noise; fleet.ACTIVITY_WINDOW_DAYS defaults to the same span. The per-can
# volume is high enough that an individual hour-of-day cell holds several
# events -- at the previous 6-28 per can a 7 x 24 grid was almost entirely
# empty cells, which is unreadable however it is coloured.
SYNTHETIC_EVENT_DAYS = 14
SYNTHETIC_EVENTS_PER_CAN = (70, 190)


def seed_models() -> dict[str, dict]:
    """Inserts the hardware SKUs, returning model_code -> row with its id."""
    models = {}
    for spec in CAN_MODELS:
        model_code = spec["model_code"]
        columns = {k: v for k, v in spec.items() if k != "model_code"}
        model_id = db.upsert_can_model(model_code, **columns)
        models[model_code] = {"model_id": model_id, **spec}
    return models


def seed_buildings() -> dict[str, int]:
    buildings = {}
    for building_code, name, campus_area, latitude, longitude, _profile in BUILDINGS:
        buildings[building_code] = db.upsert_building(
            building_code,
            name=name,
            campus_area=campus_area,
            latitude=latitude,
            longitude=longitude,
        )
    return buildings


def can_position(rng: random.Random, building_latitude: float, building_longitude: float) -> tuple[float, float]:
    """Scatters a can within roughly 40 m of its building centroid, so several
    cans in one building are individually clickable instead of stacking into a
    single pin. Approximate, like the building coordinates themselves."""
    return (
        round(building_latitude + rng.uniform(-0.00035, 0.00035), 6),
        round(building_longitude + rng.uniform(-0.00040, 0.00040), 6),
    )


def seed_cans(models: dict[str, dict], buildings: dict[str, int]) -> dict[str, dict]:
    """Inserts the physical fleet, returning can_code -> {can_id, model_code, profile}."""
    rng = random.Random(RANDOM_SEED)
    building_meta = {row[0]: row for row in BUILDINGS}
    cans = {}

    for building_code, model_codes in CAN_LAYOUT:
        _code, _name, _area, latitude, longitude, profile = building_meta[building_code]
        for index, model_code in enumerate(model_codes, start=1):
            can_code = f"{building_code}-{index:02d}"
            can_latitude, can_longitude = can_position(rng, latitude, longitude)
            can_id = db.upsert_can(
                can_code,
                model_id=models[model_code]["model_id"],
                building_id=buildings[building_code],
                floor=rng.choice(["1", "1", "1", "2", "G"]),
                placement_note=PLACEMENT_NOTES[rng.randrange(len(PLACEMENT_NOTES))],
                latitude=can_latitude,
                longitude=can_longitude,
                installed_on=datetime(2026, 1, 1) + timedelta(days=rng.randrange(0, 250)),
                lifecycle_status=LIFECYCLE_OVERRIDES.get(can_code, "active"),
                is_simulated=0 if can_code in REAL_CAN_CODES else 1,
            )
            cans[can_code] = {
                "can_id": can_id,
                "model_code": model_code,
                "profile": profile,
                "is_simulated": 0 if can_code in REAL_CAN_CODES else 1,
            }
    return cans


def _insert_batch(sql: str, rows: list[dict]) -> int:
    """One connection, one executemany, for the seed's bulk tables.

    db.py opens a connection per call, which is right for the API's single-row
    writes but costs ~0.35 s each against OCI -- a per-row telemetry tail would
    take minutes. The seed is the one caller with thousands of rows to write,
    so it batches them here rather than making db.py's helpers batch-aware for
    a case only the seed has.
    """
    if not rows:
        return 0
    with db.get_connection() as conn, conn.cursor() as cursor:
        cursor.executemany(sql, rows)
        conn.commit()
    return len(rows)


_READING_INSERT = """
INSERT INTO can_readings
    (can_id, reported_at, fill_percent, fill_source, camera_ok, actuator_ok,
     connectivity_ok, battery_percent, fault_code, fault_detail)
VALUES
    (:can_id, :reported_at, :fill_percent, :fill_source, :camera_ok, :actuator_ok,
     :connectivity_ok, :battery_percent, :fault_code, :fault_detail)
"""

_SERVICE_INSERT = """
INSERT INTO service_events (can_id, service_type, performed_at, performed_by, notes)
VALUES (:can_id, :service_type, :performed_at, :performed_by, :notes)
"""


def seed_readings(cans: dict[str, dict]) -> int:
    """Appends a 7-day telemetry tail per can that has none yet.

    A simulated can's readings carry a fill curve that climbs towards its
    seeded target. A real can's readings carry NULL fill: there are no weight
    sensors, so the hardware genuinely cannot report fullness, and that can's
    fill is counted from disposal events instead.
    """
    rng = random.Random(RANDOM_SEED + 1)
    existing = db.count_rows_by_can("can_readings")
    now = datetime.now()
    rows = []

    for can_code, can in sorted(cans.items()):
        if existing.get(can["can_id"]):
            continue

        override = HEALTH_OVERRIDES.get(can_code, {})
        target_fill = override.get("fill", rng.uniform(8.0, 62.0))
        stale_hours = override.get("stale_hours", 0)
        camera_ok = override.get("camera_ok", 1)
        actuator_ok = override.get("actuator_ok", 1)
        connectivity_ok = override.get("connectivity_ok", 1)
        fault_code = override.get("fault_code")
        fault_detail = override.get("fault_detail")
        battery = rng.uniform(46.0, 99.0)

        total = READING_TAIL_DAYS * READINGS_PER_DAY
        for step in range(total):
            age_hours = stale_hours + (total - 1 - step) * (24 / READINGS_PER_DAY)
            progress = (step + 1) / total
            if can["is_simulated"]:
                fill = max(0.0, min(100.0, target_fill * progress + rng.uniform(-3.0, 3.0)))
                fill_percent = round(fill, 1)
                fill_source = "simulated"
            else:
                fill_percent = None
                fill_source = "observed"

            # A fault is reported from the point it started rather than
            # retroactively across the whole week -- otherwise every faulted
            # can looks as if it has been broken for seven days.
            faulted = step >= total - 4
            rows.append({
                "can_id": can["can_id"],
                "reported_at": now - timedelta(hours=age_hours),
                "fill_percent": fill_percent,
                "fill_source": fill_source,
                "camera_ok": camera_ok if faulted else 1,
                "actuator_ok": actuator_ok if faulted else 1,
                "connectivity_ok": connectivity_ok if faulted else 1,
                "battery_percent": round(max(5.0, battery - progress * rng.uniform(1.0, 9.0)), 1),
                "fault_code": fault_code if faulted else None,
                "fault_detail": fault_detail if faulted else None,
            })

    return _insert_batch(_READING_INSERT, rows)


def seed_service_events(cans: dict[str, dict]) -> int:
    """Gives each can a plausible emptying history, most recently 0-4 days ago.

    A can seeded over the service threshold is emptied longer ago than the
    others, so its backlog is consistent with its fill. The two real cans are
    emptied well before their logged disposal events, so every one of those
    events counts towards their observed fill -- which is what makes them the
    cans to exercise POST /cans/{id}/service against.
    """
    rng = random.Random(RANDOM_SEED + 2)
    existing = db.count_rows_by_can("service_events")
    now = datetime.now()
    rows = []

    for can_code, can in sorted(cans.items()):
        if existing.get(can["can_id"]):
            continue

        override = HEALTH_OVERRIDES.get(can_code, {})
        if not can["is_simulated"]:
            most_recent_days = 9.0
        elif override.get("fill", 0) >= SERVICE_THRESHOLD_FILL:
            most_recent_days = rng.uniform(3.0, 4.5)
        else:
            most_recent_days = rng.uniform(0.2, 2.5)

        for occurrence in range(3):
            rows.append({
                "can_id": can["can_id"],
                "service_type": "emptied",
                "performed_at": now - timedelta(days=most_recent_days + occurrence * rng.uniform(2.5, 4.0)),
                "performed_by": rng.choice(["R. Alvarez", "T. Okafor", "M. Chen", "facilities-night-crew"]),
                "notes": None,
            })

        if override.get("fault_code"):
            rows.append({
                "can_id": can["can_id"],
                "service_type": "inspected",
                "performed_at": now - timedelta(hours=rng.uniform(2.0, 20.0)),
                "performed_by": "T. Okafor",
                "notes": f"Fault {override['fault_code']} raised; parts ordered, unit left in service.",
            })

    return _insert_batch(_SERVICE_INSERT, rows)


# Hour-of-day weights per waste profile, index 0..23. These are what make the
# usage heatmap say something: with a uniform draw every cell is the same
# colour and "when does this can heat up" has no answer, so the synthetic
# fleet is given the daily rhythm the real buildings have. Dining spikes at
# the three meal services, the library fills up in the afternoon and again
# late at night, teaching and lab space tracks class hours, residential peaks
# on the way out in the morning and on the way in at night, and the rec centre
# is an early-morning and after-work building. Overnight is near-zero
# everywhere rather than exactly zero: custodial rounds and the odd late
# passer-by do happen.
#          0  1  2  3  4  5  6   7   8   9  10  11  12  13  14  15  16  17  18  19  20  21  22  23
HOUR_WEIGHTS_BY_PROFILE = {
    "dining":      [1, 1, 0, 0, 0, 1, 3, 10, 22, 14,  8, 20, 38, 30, 12,  8, 10, 24, 34, 22, 10,  5,  3,  2],
    "library":     [6, 4, 2, 1, 1, 1, 2,  4,  8, 12, 16, 18, 16, 20, 24, 26, 24, 20, 18, 20, 22, 20, 16, 10],
    "lab":         [2, 1, 1, 0, 0, 1, 2,  6, 14, 20, 22, 20, 16, 20, 22, 20, 16, 12,  8,  6,  5,  4,  3,  2],
    "classroom":   [1, 1, 0, 0, 0, 0, 2,  6, 16, 22, 24, 22, 16, 22, 24, 20, 14,  8,  5,  3,  2,  2,  1,  1],
    "admin":       [1, 0, 0, 0, 0, 0, 2,  8, 18, 22, 22, 20, 14, 18, 20, 18, 12,  6,  2,  1,  1,  1,  1,  1],
    "residential": [8, 5, 3, 2, 1, 2, 6, 14, 18, 14, 10,  8,  8,  8,  8, 10, 14, 18, 22, 24, 26, 24, 20, 14],
    "recreation":  [2, 1, 1, 0, 0, 2, 8, 14, 16, 12, 10, 10, 12, 10, 10, 14, 22, 28, 26, 20, 14,  8,  4,  2],
}

# Day-of-week weights, index 0 = Monday .. 6 = Sunday, matching the heatmap's
# ISO row order in db.can_activity_cells. Teaching, lab and admin space
# empties out at the weekend; residential and recreation do the opposite;
# dining and the library sag but never stop.
DAY_WEIGHTS_BY_PROFILE = {
    "dining":      [10, 10, 10, 10,  9,  6,  5],
    "library":     [10, 10, 10, 10,  8,  6,  8],
    "lab":         [10, 10, 10, 10,  9,  4,  3],
    "classroom":   [10, 10, 10, 10,  8,  2,  2],
    "admin":       [10, 10, 10, 10,  9,  1,  1],
    "residential": [ 8,  8,  8,  8, 10, 10, 10],
    "recreation":  [10,  9, 10,  9,  8, 10, 10],
}


def synthetic_event_time(rng: random.Random, profile: str, now: datetime) -> datetime:
    """Draws one disposal timestamp inside the synthetic window, shaped by the
    building's daily and weekly rhythm.

    A draw that lands in the future (possible only on today's partial day) is
    moved back exactly one week, which keeps its weekday and hour -- and so the
    distribution the heatmap displays -- unchanged.
    """
    day_weights = DAY_WEIGHTS_BY_PROFILE[profile]
    days_back = rng.choices(
        range(SYNTHETIC_EVENT_DAYS),
        weights=[
            day_weights[(now - timedelta(days=offset)).weekday()]
            for offset in range(SYNTHETIC_EVENT_DAYS)
        ],
        k=1,
    )[0]
    hour = rng.choices(range(24), weights=HOUR_WEIGHTS_BY_PROFILE[profile], k=1)[0]

    day = (now - timedelta(days=days_back)).replace(
        hour=hour, minute=rng.randrange(60), second=rng.randrange(60), microsecond=0
    )
    if day > now:
        day -= timedelta(days=7)
    return day


def weighted_category(rng: random.Random, profile: str) -> str:
    weights = PROFILE_CATEGORY_WEIGHTS[profile]
    categories = [category for category, _ in weights]
    return rng.choices(categories, weights=[weight for _, weight in weights], k=1)[0]


def seed_waste_events(cans: dict[str, dict]) -> int:
    """Gives each can some contents, so clicking a pin shows a real category
    split rather than an empty panel.

    These rows are synthetic: they carry no IMAGE_KEY (there is no captured
    photo behind them) and their LOCATION is the can's own code, which is how
    they stay distinguishable from events the live pipeline logged. A can that
    already has events attributed to it -- including the two real cans, whose
    events came from the live pipeline -- is skipped.

    PRODUCT_ID is resolved through db.match_product, the same token-overlap
    matcher the live pipeline uses, rather than being assigned by hand. So the
    per-can estimated-value figure comes from a real catalog match against a
    real PRODUCTS row, and a can shows no value when nothing in it matches the
    catalog -- which is the truth for most of this fleet.

    CREATED_AT is drawn from the building's daily and weekly rhythm (see
    synthetic_event_time) rather than uniformly across the window, so the usage
    heatmap has a real pattern to show. A database already holding
    uniformly-timed rows from an earlier seed run is not touched here, since
    this function skips any can that already has events -- use
    reshape_event_times for those.
    """
    rng = random.Random(RANDOM_SEED + 3)
    existing = db.count_waste_events_by_can()
    now = datetime.now()
    rows = []
    product_cache: dict[str, int | None] = {}

    for can_code, can in sorted(cans.items()):
        if existing.get(can["can_id"]) or not can["is_simulated"]:
            continue
        count = rng.randrange(*SYNTHETIC_EVENTS_PER_CAN)
        for _ in range(count):
            category = weighted_category(rng, can["profile"])
            detected_object = rng.choice(OBJECTS_BY_CATEGORY[category])
            if detected_object not in product_cache:
                match = db.match_product(detected_object)
                product_cache[detected_object] = match["product_id"] if match else None
            rows.append({
                "detected_object": detected_object,
                "material": MATERIAL_BY_CATEGORY[category],
                "category": category,
                "location": can_code,
                "confidence": rng.randrange(62, 96),
                "created_at": synthetic_event_time(rng, can["profile"], now),
                "bin_id": can["can_id"],
                "product_id": product_cache[detected_object],
            })

    return _insert_batch(_SYNTHETIC_EVENT_INSERT, rows)



_SYNTHETIC_EVENT_SELECT = """
SELECT we.event_id, we.bin_id
FROM waste_events we
JOIN cans c ON c.can_id = we.bin_id
WHERE we.image_key IS NULL
  AND we.location = c.can_code
"""

_SYNTHETIC_TIME_UPDATE = """
UPDATE waste_events SET created_at = :created_at WHERE event_id = :event_id
"""


def reshape_event_times(cans: dict[str, dict]) -> int:
    """Rewrites CREATED_AT on existing synthetic disposals to follow the daily
    and weekly rhythm in synthetic_event_time.

    Opt-in (`python seed_campus.py --reshape-times`) because unlike the rest of
    this module it mutates rows rather than skipping them. It is needed when a
    database was seeded by an earlier version, whose uniform 0-96 h draw leaves
    the usage heatmap a flat wash with one spike at whatever hour the seed was
    run -- a correct rendering of data that has no pattern in it.

    Only synthetic rows are touched, identified exactly as seed_waste_events
    writes them: no IMAGE_KEY, and a LOCATION equal to the can's own code.
    Events the live pipeline logged keep their real capture times, which are
    the only observed timestamps in the table and must not be invented over.
    """
    profile_by_can_id = {can["can_id"]: can["profile"] for can in cans.values()}
    rng = random.Random(RANDOM_SEED + 4)
    now = datetime.now()

    with db.get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(_SYNTHETIC_EVENT_SELECT)
        targets = cursor.fetchall()
        rows = [
            {
                "event_id": event_id,
                "created_at": synthetic_event_time(rng, profile_by_can_id[bin_id], now),
            }
            for event_id, bin_id in targets
            if bin_id in profile_by_can_id
        ]
        if not rows:
            return 0
        cursor.executemany(_SYNTHETIC_TIME_UPDATE, rows)
        conn.commit()
    return len(rows)



def refresh_readings(cans: dict[str, dict]) -> int:
    """Appends one current reading per can, so a fleet seeded days ago stops
    reading as entirely offline.

    The telemetry tail seed_readings writes ends at the moment it ran. Cans
    are judged offline after FLEET_STALE_MINUTES (90 by default), so a demo
    database left overnight shows all 43 units grey and the map's status
    colours carry no information. Re-running the seed does not help: that
    function deliberately skips any can that already has readings.

    This appends rather than rewriting, which keeps the detail panel's history
    chart intact, and it reproduces each can's intended end state from
    HEALTH_OVERRIDES rather than inventing a new one -- so the faults, the
    over-threshold fills and the two deliberately-silent units all survive the
    refresh and the map keeps the health mix the demo is built around.
    """
    rng = random.Random(RANDOM_SEED + 5)
    now = datetime.now()
    rows = []

    for can_code, can in sorted(cans.items()):
        override = HEALTH_OVERRIDES.get(can_code, {})
        # A can seeded as silent stays silent: its "current" reading is still
        # stale_hours old, which is the whole point of that override.
        stale_hours = override.get("stale_hours", 0)
        target_fill = override.get("fill", rng.uniform(8.0, 62.0))

        rows.append({
            "can_id": can["can_id"],
            "reported_at": now - timedelta(hours=stale_hours),
            "fill_percent": round(target_fill, 1) if can["is_simulated"] else None,
            "fill_source": "simulated" if can["is_simulated"] else "observed",
            "camera_ok": override.get("camera_ok", 1),
            "actuator_ok": override.get("actuator_ok", 1),
            "connectivity_ok": override.get("connectivity_ok", 1),
            "battery_percent": round(rng.uniform(42.0, 97.0), 1),
            "fault_code": override.get("fault_code"),
            "fault_detail": override.get("fault_detail"),
        })

    return _insert_batch(_READING_INSERT, rows)


def main() -> None:
    reshape = "--reshape-times" in sys.argv
    refresh = "--refresh-readings" in sys.argv
    print("Seeding campus fleet (coordinates are APPROXIMATE -- see module docstring).")

    models = seed_models()
    print(f"  can models:      {len(models)}")

    buildings = seed_buildings()
    print(f"  buildings:       {len(buildings)}")

    cans = seed_cans(models, buildings)
    print(f"  cans:            {len(cans)}")

    backfilled = db.backfill_waste_event_bin_ids(LEGACY_LOCATION_TO_CAN_CODE)
    for location, updated in backfilled.items():
        print(f"  backfilled BIN_ID for {updated} event(s) at location {location!r}")

    print(f"  readings:        {seed_readings(cans)} new")
    if refresh:
        print(f"  refreshed:       {refresh_readings(cans)} current reading(s)")
    print(f"  service events:  {seed_service_events(cans)} new")
    print(f"  synthetic events:{seed_waste_events(cans)} new")
    if reshape:
        print(f"  reshaped times:  {reshape_event_times(cans)} synthetic event(s)")
    print("Done.")


if __name__ == "__main__":
    main()
