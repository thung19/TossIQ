"""Initiatives: measurable goals over the organization's own waste data,
and the projects that move them.

The decision this module exists to enforce is that an initiative stores a
MEASUREMENT RECIPE rather than a number. METRIC names a quantity and the
scope columns name a slice; progress is recomputed from logged disposals on
every read. A target tracked by hand drifts from reality the first week
somebody is busy, and a dashboard reporting a stale number is worse than one
reporting none.

Every metric here is already computed somewhere else in the product --
diversion on the analytics overview, contamination on the quality tab,
hazards on the hazards page. They are reused rather than reimplemented, so
an initiative's "current" figure is the same number the rest of the app
shows for the same slice. A goal that disagrees with the dashboard it sits
next to is a goal nobody will trust.

Progress is honest about going backwards. An initiative whose current value
is worse than its baseline reports negative progress rather than clamping to
zero: "no progress" and "actively losing ground" are different facts and the
second one is the one worth knowing.
"""

from datetime import datetime

import analytics
import db

# Each metric knows how to measure itself over a scope, what unit it is in,
# and whether more is better by default. `measure` takes the resolved scope
# filters plus a window and returns a float.
#
# `lower_is_better` is the DEFAULT direction offered in the UI, not a rule:
# the initiative stores its own direction, because a university might
# genuinely want to increase compost tonnage while another wants to cut it.


def _totals(filters: dict) -> dict:
    return db.analytics_totals(**filters)


def _measure_items(filters: dict) -> float:
    return float(_totals(filters)["n"])


def _measure_cost(filters: dict) -> float:
    row = _totals(filters)
    return round(row["matched_cost"] + row["class_cost"], 2)


def _measure_mass(filters: dict) -> float:
    row = _totals(filters)
    return round((row["matched_grams"] + row["class_grams"]) / 1000.0, 2)


def _measure_diversion(filters: dict) -> float:
    return analytics.overview(**filters)["diversion_rate"]


def _measure_landfill_items(filters: dict) -> float:
    return float(_totals({**filters, "category": "landfill"})["n"])


def _measure_contamination(filters: dict) -> float:
    return analytics.misrouted(**filters)["misrouted_rate"]


def _measure_hazards(filters: dict) -> float:
    return float(_totals(filters)["hazard_n"])


def _measure_accuracy(filters: dict) -> float:
    report = analytics.accuracy(**filters)
    # None means nobody has reviewed anything in scope. Zero would read as
    # "the classifier got everything wrong", which is a different claim.
    return report["accuracy"] if report["accuracy"] is not None else 0.0


METRICS = {
    "items": {
        "label": "Items discarded",
        "unit": "items",
        "format": "count",
        "lower_is_better": True,
        "measure": _measure_items,
        "help": "Every disposal logged in scope. The broadest reduction goal.",
    },
    "landfill_items": {
        "label": "Items sent to landfill",
        "unit": "items",
        "format": "count",
        "lower_is_better": True,
        "measure": _measure_landfill_items,
        "help": "Disposals logged into the landfill stream, ignoring scope category.",
    },
    "cost": {
        "label": "Estimated cost discarded",
        "unit": "$",
        "format": "money",
        "lower_is_better": True,
        "measure": _measure_cost,
        "help": "Catalog loss-on-discard for items in scope. An estimate, not a ledger.",
    },
    "mass": {
        "label": "Estimated mass discarded",
        "unit": "kg",
        "format": "mass",
        "lower_is_better": True,
        "measure": _measure_mass,
        "help": "Items times catalog reference mass. No can has a weight sensor.",
    },
    "diversion_rate": {
        "label": "Diversion rate",
        "unit": "%",
        "format": "percent",
        "lower_is_better": False,
        "measure": _measure_diversion,
        "help": "Share of disposals going to recycling or compost rather than landfill.",
    },
    "contamination_rate": {
        "label": "Stream contamination",
        "unit": "%",
        "format": "percent",
        "lower_is_better": True,
        "measure": _measure_contamination,
        "help": "Share of items logged into a stream their catalog entry disagrees with.",
    },
    "hazard_events": {
        "label": "Hazardous items found",
        "unit": "items",
        "format": "count",
        "lower_is_better": True,
        "measure": _measure_hazards,
        "help": "Disposals the vision model flagged as hazardous.",
    },
    "review_accuracy": {
        "label": "Classifier agreement",
        "unit": "%",
        "format": "percent",
        "lower_is_better": False,
        "measure": _measure_accuracy,
        "help": "Agreement with human reviewers, over the reviewed sample only.",
    },
}

STATUSES = ("active", "achieved", "paused", "archived")
PROJECT_STATUSES = ("proposed", "in_progress", "blocked", "done", "cancelled")

SCOPE_FIELDS = (
    ("scope_building_id", "building_id"),
    ("scope_category", "category"),
    ("scope_material", "material"),
    ("scope_object", "detected_object"),
    ("scope_supplier", "supplier"),
)


def scope_filters(initiative: dict, days: int) -> dict:
    """Turns an initiative's stored scope into the analytics filter set.

    One mapping, so a goal can only ever be defined over a slice the
    analytics page can also show -- which is what lets somebody click
    through from a target to the data behind it.
    """
    filters = {"days": days}
    for column, filter_name in SCOPE_FIELDS:
        value = initiative.get(column)
        if value not in (None, ""):
            filters[filter_name] = value
    return filters


def describe_scope(initiative: dict, building_names: dict[int, str] | None = None) -> str:
    """A human sentence for the slice, for the card header."""
    parts = []
    building_id = initiative.get("scope_building_id")
    if building_id:
        parts.append((building_names or {}).get(building_id, f"building {building_id}"))
    for column, label in (
        ("scope_category", None),
        ("scope_material", None),
        ("scope_object", None),
        ("scope_supplier", "from"),
    ):
        value = initiative.get(column)
        if value:
            parts.append(f"{label} {value}" if label else str(value))
    return " · ".join(parts) if parts else "campus-wide"


def measure(initiative: dict, days: int | None = None) -> float | None:
    """The metric's current value over the initiative's scope.

    Returns None for an unknown metric rather than raising: a single
    initiative created against a metric that has since been removed should
    show as unmeasurable, not take the page down with it.
    """
    spec = METRICS.get(initiative.get("metric"))
    if spec is None:
        return None
    window = days or initiative.get("baseline_window_days") or 30
    return spec["measure"](scope_filters(initiative, window))


def progress(initiative: dict, current: float | None) -> dict:
    """How far along, as a fraction of the distance from baseline to target.

    Deliberately not "current over target": for a reduction goal that ratio
    is above 1 when you are failing, which reads as success. Measuring the
    journey from where you started makes both directions legible, and lets
    the answer go negative when a number is moving the wrong way -- "no
    progress" and "actively losing ground" are different facts.
    """
    baseline = initiative.get("baseline_value")
    target = initiative.get("target_value")
    if current is None or baseline is None or target is None:
        return {"percent": None, "state": "unmeasured", "distance_to_target": None}

    span = target - baseline
    if abs(span) < 1e-9:
        # The baseline already sits on the target. Either it was set that
        # way, or the goal was hit before anyone looked.
        reached = (
            current <= target
            if initiative.get("direction", "reduce") == "reduce"
            else current >= target
        )
        return {
            "percent": 100.0 if reached else 0.0,
            "state": "achieved" if reached else "off_track",
            "distance_to_target": round(target - current, 3),
        }

    percent = round((current - baseline) / span * 100.0, 1)
    reduce = initiative.get("direction", "reduce") == "reduce"
    reached = current <= target if reduce else current >= target

    if reached:
        state = "achieved"
    elif percent < 0:
        state = "regressing"
    elif percent < 35:
        state = "off_track"
    elif percent < 80:
        state = "in_progress"
    else:
        state = "near_target"

    return {
        "percent": percent,
        "state": state,
        "distance_to_target": round(target - current, 3),
    }


def days_remaining(target_date: str | None, now: datetime | None = None) -> int | None:
    if not target_date:
        return None
    now = now or datetime.now()
    target = datetime.strptime(target_date, "%Y-%m-%d")
    return (target.date() - now.date()).days


def resolve(initiative: dict, projects: list[dict], building_names: dict[int, str],
            now: datetime | None = None) -> dict:
    """Decorates one stored initiative with its live measurement, progress
    and the state of the work under it."""
    spec = METRICS.get(initiative.get("metric"), {})
    current = measure(initiative)
    advance = progress(initiative, current)
    remaining = days_remaining(initiative.get("target_date"), now=now)

    by_status: dict[str, int] = {}
    for project in projects:
        by_status[project["status"]] = by_status.get(project["status"], 0) + 1

    # Expected impact is what the projects CLAIM they will contribute. It is
    # reported beside measured progress and never added to it: a pile of
    # optimistic estimates must not read as achievement.
    claimed = sum(
        project.get("expected_impact") or 0.0
        for project in projects
        if project["status"] in ("in_progress", "done")
    )

    return {
        **initiative,
        "metric_label": spec.get("label", initiative.get("metric")),
        "unit": spec.get("unit", ""),
        "format": spec.get("format", "count"),
        "metric_help": spec.get("help", ""),
        "scope_label": describe_scope(initiative, building_names),
        "current_value": current,
        "progress_percent": advance["percent"],
        "progress_state": advance["state"],
        "distance_to_target": advance["distance_to_target"],
        "days_remaining": remaining,
        # A goal with no work under it is a wish, and the page says so
        # rather than showing an encouraging bar.
        "project_count": len(projects),
        "projects_by_status": by_status,
        "projects_done": by_status.get("done", 0),
        "projects_active": by_status.get("in_progress", 0),
        "claimed_impact": round(claimed, 2) if claimed else 0.0,
        "projects": projects,
    }


def list_resolved(status: str | None = None, now: datetime | None = None) -> dict:
    """Every initiative with live progress, plus the roll-up the page heads
    with."""
    initiatives = db.list_initiatives(status=status)
    projects = db.list_projects()
    building_names = {b["building_id"]: b["name"] for b in db.list_buildings()}

    by_initiative: dict[int, list[dict]] = {}
    for project in projects:
        by_initiative.setdefault(project["initiative_id"], []).append(project)

    resolved = [
        resolve(initiative, by_initiative.get(initiative["initiative_id"], []),
                building_names, now=now)
        for initiative in initiatives
    ]

    states: dict[str, int] = {}
    for item in resolved:
        states[item["progress_state"]] = states.get(item["progress_state"], 0) + 1

    unbacked = [item for item in resolved
                if item["status"] == "active" and item["project_count"] == 0]
    overdue = [
        item for item in resolved
        if item["status"] == "active"
        and item["days_remaining"] is not None
        and item["days_remaining"] < 0
        and item["progress_state"] != "achieved"
    ]

    return {
        "initiatives": resolved,
        "total": len(resolved),
        "by_state": states,
        "achieved": states.get("achieved", 0),
        "regressing": states.get("regressing", 0),
        "unbacked": [
            {"initiative_id": item["initiative_id"], "name": item["name"]}
            for item in unbacked
        ],
        "overdue": [
            {"initiative_id": item["initiative_id"], "name": item["name"],
             "days_overdue": -item["days_remaining"]}
            for item in overdue
        ],
        "metrics": {
            key: {k: v for k, v in spec.items() if k != "measure"}
            for key, spec in METRICS.items()
        },
        "note": (
            "Progress is measured from logged disposals every time this page loads, "
            "over each goal's own scope and window. Baselines are frozen at creation; "
            "project impact is what the work claims it will contribute and is never "
            "added to measured progress."
        ),
    }
