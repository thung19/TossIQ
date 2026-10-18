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
STALE_MINUTES = int(os.environ.get("FLEET_STALE_MINUTES", "90"))

# Fill at or above this percentage puts a can on the service list.
SERVICE_THRESHOLD_PERCENT = float(os.environ.get("FLEET_SERVICE_THRESHOLD_PERCENT", "80"))

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
