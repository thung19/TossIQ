"""Fleet status derivation for the campus can map.

This module owns the single canonical answer to "what is wrong with this can".
The derivation lives here and nowhere else -- in particular it is NOT
reimplemented in TypeScript; the frontend renders the status and reasons the
API hands it, so a threshold change here changes the map without a frontend
edit.

Two things are derived rather than measured:

* Fill. There are no weight sensors (CLAUDE.md records that as a hard hardware
  constraint), so a can's fullness is either counted from the disposal events
  attributed to it since it was last emptied ('observed'), or carried from a
  seeded reading for a can that does not physically exist ('simulated'), or
  absent, for a can with neither ('unknown') -- which is reported rather than
  a zero the system never observed. Every fill value travels with its
  FILL_SOURCE so the UI can keep the three apart, per CLAUDE.md's requirement
  that observed data stay distinguishable from estimates.
* Status. A can reports its single worst status, which colours one map pin,
  plus the full list of reasons, which the detail panel explains.
"""

import os
from datetime import datetime, timedelta

import db

# A can that has not reported within this window is treated as offline rather
# than as healthy-but-quiet: silence from a unit that is supposed to report
# every few minutes is itself the fault worth showing.
STALE_MINUTES = int(os.environ.get("FLEET_STALE_MINUTES") or "90")

# Fill at or above this percentage puts a can on the service list.
SERVICE_THRESHOLD_PERCENT = float(os.environ.get("FLEET_SERVICE_THRESHOLD_PERCENT") or "80")

# Worst-first. A can that is both offline and over the fill threshold shows as
# offline, because the fill number cannot be trusted while the unit is silent.
STATUS_SEVERITY = {"offline": 3, "fault": 2, "needs_service": 1, "ok": 0}

SERVICE_TYPES = ("emptied", "repaired", "camera_replaced", "inspected")


def derived_fill_percent(events_since_emptied: int, capacity_items: int | None) -> float | None:
    """Fill counted in items: disposals attributed to this can since it was last
    emptied, over the model's item capacity, capped at 100.

    Returns None when the model declares no item capacity, since a percentage
    of an unknown denominator would be a fabricated number, and when no
    disposal is attributed to the can at all: with no weight sensor, nothing to
    count means nothing is known about its fullness, not that it is empty.
    """
    if not capacity_items or events_since_emptied <= 0:
        return None
    percent = 100.0 * events_since_emptied / capacity_items
    return round(min(percent, 100.0), 1)


def resolve_fill(can_row: dict) -> tuple[float | None, str]:
    """Picks the fill value to present for one can, and says where it came from.

    Simulated cans carry the fill_percent of their latest seeded reading.
    Real reporting cans ignore any seeded value and use the item count, which
    is the only fill signal this hardware can actually observe.

    A can with no fill signal at all reports (None, "unknown") rather than a
    zero: 0% observed is a claim about the can, and claiming it for a can
    nothing is attributed to would be a confidently wrong number.
    """
    if can_row.get("is_simulated"):
        reading_fill = can_row.get("fill_percent")
        if reading_fill is None:
            return None, "unknown"
        return round(float(reading_fill), 1), "simulated"

    derived = derived_fill_percent(
        can_row.get("events_since_emptied") or 0, can_row.get("capacity_items")
    )
    if derived is None:
        return None, "unknown"
    return derived, "observed"


def resolve_status(
    can_row: dict,
    fill_percent: float | None = None,
    now: datetime | None = None,
    stale_minutes: int | None = None,
    service_threshold: float | None = None,
) -> dict:
    """Resolves one can's worst status plus every reason that applies.

    `can_row` carries the can's latest reading fields flattened onto it
    (reported_at, connectivity_ok, camera_ok, actuator_ok, fault_code,
    fault_detail); a can with no reading at all has reported_at None.

    Pure: takes a row and a clock, touches no database, so the thresholds and
    the severity ordering are testable without OCI.
    """
    now = now or datetime.now()
    stale_minutes = STALE_MINUTES if stale_minutes is None else stale_minutes
    service_threshold = (
        SERVICE_THRESHOLD_PERCENT if service_threshold is None else service_threshold
    )

    triggered: list[tuple[str, str]] = []

    reported_at = can_row.get("reported_at")
    if reported_at is None:
        triggered.append(("offline", "No telemetry has ever been reported"))
    else:
        age = now - reported_at
        if age > timedelta(minutes=stale_minutes):
            triggered.append((
                "offline",
                f"Last reported {_describe_age(age)} ago, over the {stale_minutes} min staleness limit",
            ))
        if can_row.get("connectivity_ok") == 0:
            triggered.append(("offline", "Unit reported its uplink as down"))

    if can_row.get("camera_ok") == 0:
        triggered.append(("fault", "Camera not responding"))
    if can_row.get("actuator_ok") == 0:
        triggered.append(("fault", "Sorting actuator not responding"))
    fault_code = can_row.get("fault_code")
    if fault_code:
        detail = can_row.get("fault_detail")
        triggered.append(("fault", f"Hardware fault {fault_code}" + (f": {detail}" if detail else "")))

    if fill_percent is not None and fill_percent >= service_threshold:
        triggered.append((
            "needs_service",
            f"Fill at {fill_percent:.0f}%, at or over the {service_threshold:.0f}% service threshold",
        ))

    if not triggered:
        return {"status": "ok", "reasons": []}

    triggered.sort(key=lambda pair: STATUS_SEVERITY[pair[0]], reverse=True)
    return {"status": triggered[0][0], "reasons": [reason for _, reason in triggered]}


def _describe_age(age: timedelta) -> str:
    minutes = int(age.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h"
    return f"{hours // 24} d"


def resolve_can(can_row: dict, now: datetime | None = None) -> dict:
    """Decorates one raw can row with its resolved fill and status.

    The returned dict is what the API serves: the stored columns plus
    fill_percent / fill_source / status / status_reasons.
    """
    fill_percent, fill_source = resolve_fill(can_row)
    status = resolve_status(can_row, fill_percent=fill_percent, now=now)
    return {
        **can_row,
        "fill_percent": fill_percent,
        "fill_source": fill_source,
        "status": status["status"],
        "status_reasons": status["reasons"],
    }


# ---------------------------------------------------------------------------
# Assembly over db.py's queries
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Telemetry heartbeat for the simulated fleet
# ---------------------------------------------------------------------------
# The mock cans stand for hardware that would report every few minutes. They
# do not, because nothing was writing for them: seed_campus wrote one tail
# and stopped, so the whole fleet aged past STALE_MINUTES and read as
# offline within a couple of hours, every time. Refreshing by hand fixed it
# until lunchtime and then it broke again.
#
# This is the missing writer. It appends a current reading for any simulated
# can that is drifting towards stale, reproducing that can's intended health
# from the seed's overrides so the demo keeps the mix it was built to show:
# mostly fine, a few needing service, a few faulted, a couple genuinely
# silent.
#
# Real reporting cans are never touched. Their silence is a fact about
# hardware, and inventing a heartbeat for a unit that is not sending one
# would be the monitoring system lying about the thing it exists to watch.

# Written for at half the staleness window, so a can is topped up well
# before it would be judged offline rather than flickering on the boundary.
HEARTBEAT_FRACTION = 0.5


def due_for_heartbeat(cans: list[dict], now: datetime | None = None) -> list[dict]:
    """Simulated cans whose last reading is old enough to be worth renewing.

    Cans the seed deliberately silenced are excluded by their own override,
    not by this filter: `stale_hours` is reapplied when the reading is
    written, so they go back to being exactly as stale as they are meant to
    be.
    """
    now = now or datetime.now()
    cutoff = timedelta(minutes=STALE_MINUTES * HEARTBEAT_FRACTION)
    due = []
    for can in cans:
        if not can.get("is_simulated"):
            continue
        reported_at = can.get("reported_at")
        if reported_at is None or (now - reported_at) >= cutoff:
            due.append(can)
    return due


def send_heartbeat(now: datetime | None = None) -> int:
    """Writes a current reading for every simulated can that needs one.

    Returns the number written. Importing the seed here rather than at
    module load keeps fleet.py usable without it, and keeps the health mix
    defined in exactly one place: the seed's HEALTH_OVERRIDES, which is
    what the demo fleet is described by everywhere else.
    """
    import random

    import seed_campus

    now = now or datetime.now()
    rows = db.list_can_rows()
    due = due_for_heartbeat(rows, now=now)
    if not due:
        return 0

    rng = random.Random()
    readings = [
        seed_campus.reading_for(can["can_code"], can, rng, now) for can in due
    ]
    return db.insert_can_readings(readings)


def list_fleet(
    status: str | None = None,
    building_id: int | None = None,
    model_id: int | None = None,
) -> list[dict]:
    """The map's single payload: every active can with its resolved status.

    building_id / model_id narrow the SQL; `status` is applied here because
    status is derived rather than stored.
    """
    rows = db.list_can_rows(building_id=building_id, model_id=model_id)
    now = datetime.now()
    cans = [resolve_can(row, now=now) for row in rows]
    if status:
        cans = [can for can in cans if can["status"] == status]
    return cans


def get_can_detail(can_id: int, reading_limit: int = 200, service_limit: int = 20) -> dict | None:
    """One can in full: resolved status, the reading tail the detail panel
    charts, and its service history."""
    rows = db.list_can_rows(can_id=can_id)
    if not rows:
        return None
    can = resolve_can(rows[0])
    can["readings"] = db.list_can_readings(can_id, limit=reading_limit)
    can["service_events"] = db.list_service_events(can_id, limit=service_limit)
    return can


def fleet_summary(building_id: int | None = None, model_id: int | None = None) -> dict:
    """Counts by status for the map's KPI row and the filter chips.

    Takes the same building_id / model_id narrowing the fleet list takes, so
    the counts shown beside a filtered map describe the cans on that map
    rather than the whole campus.
    """
    cans = list_fleet(building_id=building_id, model_id=model_id)
    counts = {name: 0 for name in STATUS_SEVERITY}
    for can in cans:
        counts[can["status"]] += 1
    simulated = sum(1 for can in cans if can["is_simulated"])
    return {
        "total": len(cans),
        "by_status": counts,
        "simulated": simulated,
        "observed": len(cans) - simulated,
        "stale_minutes": STALE_MINUTES,
        "service_threshold_percent": SERVICE_THRESHOLD_PERCENT,
    }


# ---------------------------------------------------------------------------
# Usage heatmap -- when, not just where
# ---------------------------------------------------------------------------
# Same rule as status: the shaping lives here, the frontend only paints what
# it is handed. In particular the colour scale's upper bound (`max_cell` /
# `max_can`) is computed here, so the map and the grid are normalised against
# the same denominator and a hot can looks hot on both.

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# How far back the heatmap looks by default. Two weeks is the shortest window
# that gives every weekday at least two samples, which is what makes a
# "Tuesdays are quiet" reading mean anything rather than being one day's noise.
ACTIVITY_WINDOW_DAYS = 14


def activity_heatmap(
    days: int = ACTIVITY_WINDOW_DAYS,
    building_id: int | None = None,
    model_id: int | None = None,
) -> dict:
    """When the fleet gets used, over the same scope the map is showing.

    Returns three views of one query, because the UI needs all three and
    recomputing them in TypeScript would be the duplicated-derivation mistake
    this module exists to avoid:

    * `cells`   -- sparse (can, weekday, hour) counts. The client filters these
                   to recolour the map for a selected time bucket.
    * `day_hour`-- a dense 7 x 24 grid summed over cans: the heatmap itself.
    * `by_can`  -- totals per can over the whole window, for the default map
                   intensity when no bucket is selected.

    Every number here is counted from logged disposal events. There are no
    weight sensors, so this is usage *frequency*, not volume, and the API
    labels it as such rather than implying it measures how full a can gets.
    """
    cells = db.can_activity_cells(days=days, building_id=building_id, model_id=model_id)

    day_hour = [[0] * 24 for _ in range(7)]
    by_can: dict[int, int] = {}
    by_hour = [0] * 24
    by_day = [0] * 7

    for cell in cells:
        day, hour, count = cell["day_of_week"], cell["hour_of_day"], cell["count"]
        day_hour[day][hour] += count
        by_hour[hour] += count
        by_day[day] += count
        by_can[cell["can_id"]] = by_can.get(cell["can_id"], 0) + count

    total = sum(by_hour)
    max_cell = max((max(row) for row in day_hour), default=0)
    max_can = max(by_can.values(), default=0)

    # The colour scale is bounded by a high percentile of the non-empty cells,
    # not by the maximum. One real burst -- the live camera logged 294 items
    # into a single hour during a demo run -- is a true observation and keeps
    # its timestamps, but scaling 168 cells against it renders every ordinary
    # hour the same near-black and destroys exactly the pattern the heatmap
    # exists to show. Cells above the bound are reported as over-scale instead
    # of being clipped silently, so the outlier is still visible as an outlier.
    scale_max_cell = _percentile([count for row in day_hour for count in row if count > 0], 0.95)
    scale_max_can = _percentile([count for count in by_can.values() if count > 0], 0.95)

    # The headline "when does it get busy" figure is the median across the
    # seven weekdays for each hour, not the largest single bucket. A one-off
    # burst -- the live camera logged 294 items into one hour during a demo
    # run -- is the largest bucket by a wide margin and would otherwise be
    # reported as the campus's busy time, which it plainly is not. A median
    # needs the same hour to be busy on most days before it moves.
    typical_by_hour = [_median([day_hour[day][hour] for day in range(7)]) for hour in range(24)]
    typical_peak = None
    if any(typical_by_hour):
        hour = typical_by_hour.index(max(typical_by_hour))
        typical_peak = {"hour_of_day": hour, "count": typical_by_hour[hour]}

    peak = None
    if max_cell > 0:
        for day in range(7):
            for hour in range(24):
                if day_hour[day][hour] == max_cell:
                    peak = {
                        "day_of_week": day,
                        "day_name": DAY_NAMES[day],
                        "hour_of_day": hour,
                        "count": max_cell,
                    }
                    break
            if peak:
                break

    return {
        "window_days": days,
        "total_events": total,
        "cells": cells,
        "day_hour": day_hour,
        "by_hour": by_hour,
        "by_day": by_day,
        "by_can": [{"can_id": can_id, "count": count} for can_id, count in sorted(by_can.items())],
        "max_cell": max_cell,
        "max_can": max_can,
        "scale_max_cell": scale_max_cell,
        "scale_max_can": scale_max_can,
        "peak": peak,
        "typical_by_hour": typical_by_hour,
        "typical_peak": typical_peak,
        "day_names": list(DAY_NAMES),
    }




def _median(values: list[int]) -> int:
    """Integer median. These are event counts, and a "busiest hour: 6.5 items"
    readout would imply a precision the half-step does not carry, so the lower
    of the two middles is taken for an even-length list rather than averaging.
    """
    if not values:
        return 0
    return sorted(values)[(len(values) - 1) // 2]


def _percentile(values: list[int], fraction: float) -> int:
    """Nearest-rank percentile, floored at 1 so a scale bound is never zero.

    Deliberately not statistics.quantiles: that interpolates, and these are
    event counts -- a bound of 7.4 items is not a thing the legend can label.
    """
    if not values:
        return 1
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return max(1, ordered[index])


def activity_for_bucket(
    cells: list[dict], day_of_week: int | None = None, hour_of_day: int | None = None
) -> dict[int, int]:
    """Per-can counts inside one slice of the heatmap.

    Either coordinate may be left open: (day=1, hour=None) is "all of Tuesday",
    (day=None, hour=12) is "noon on every day", and both None is the whole
    window. Exposed for the API's tests and as the reference the frontend's
    identical client-side filter is checked against.
    """
    totals: dict[int, int] = {}
    for cell in cells:
        if day_of_week is not None and cell["day_of_week"] != day_of_week:
            continue
        if hour_of_day is not None and cell["hour_of_day"] != hour_of_day:
            continue
        totals[cell["can_id"]] = totals.get(cell["can_id"], 0) + cell["count"]
    return totals
