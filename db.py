"""OCI Autonomous DB access layer for TossIQ.

All disposal-event persistence, catalog (PRODUCTS) lookups, recommendation
storage, and campus-fleet inventory queries go through here. Kept deliberately
thin: plain SQL over python-oracledb, no ORM, since the schema is small.

WASTE_EVENTS / PRODUCTS / RECOMMENDATIONS predate this repository tracking its
own DDL and exist in OCI without tracked definitions. The campus-fleet tables
(CAN_MODELS / BUILDINGS / CANS / CAN_READINGS / SERVICE_EVENTS, and
WASTE_EVENTS.BIN_ID) are defined in schema/ and applied by schema/apply.py.

Connections are opened per call rather than pooled -- simplest thing that
works for a hackathon demo's request volume. Swap for a oracledb.create_pool()
if this becomes a bottleneck.
"""

import os
from contextlib import contextmanager

import oracledb
from dotenv import load_dotenv

load_dotenv()


@contextmanager
def get_connection():
    wallet_dir = os.environ["DB_WALLET_DIR"]
    connection = oracledb.connect(
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dsn=os.environ["DB_DSN"],
        config_dir=wallet_dir,
        wallet_location=wallet_dir,
        wallet_password=os.environ["DB_WALLET_PASSWORD"],
    )
    try:
        yield connection
    finally:
        connection.close()


# ---------------------------------------------------------------------------
# Catalog (PRODUCTS) -- organization-specific item recognition (Experience 3)
# ---------------------------------------------------------------------------

def add_product(product_name, supplier=None, sku=None, material=None, unit_cost=None) -> int:
    with get_connection() as conn, conn.cursor() as cursor:
        product_id_var = cursor.var(int)
        cursor.execute(
            """
            INSERT INTO products (product_name, supplier, sku, material, unit_cost)
            VALUES (:product_name, :supplier, :sku, :material, :unit_cost)
            RETURNING product_id INTO :product_id
            """,
            product_name=product_name,
            supplier=supplier,
            sku=sku,
            material=material,
            unit_cost=unit_cost,
            product_id=product_id_var,
        )
        conn.commit()
        return product_id_var.getvalue()[0]


def list_products() -> list[dict]:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT product_id, product_name, supplier, sku, material, unit_cost FROM products ORDER BY product_name"
        )
        cols = [d[0].lower() for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


_STOPWORDS = {"the", "a", "an", "of", "and", "or", "for", "with", "disposable", "item"}


def _significant_words(text: str) -> set[str]:
    words = {w.strip(".,!?") for w in text.lower().split()}
    return {w for w in words if len(w) >= 4 and w not in _STOPWORDS}


def match_product(detected_object: str | None) -> dict | None:
    """Best-effort catalog match: token-overlap against product_name.

    Deliberately simple (no embeddings/retraining needed per catalog item,
    per PRD section 2C) -- the vision model's free-text description just
    needs to share at least one distinctive word with an organization's
    product name, e.g. "disposable plastic fork" matching catalog entry
    "Dining Hall Disposable Fork" on the word "fork". Returns the catalog
    entry with the most overlapping words (ties broken by longer name, i.e.
    the more specific entry).
    """
    if not detected_object:
        return None
    detected_words = _significant_words(detected_object)
    if not detected_words:
        return None

    best = None
    best_score = 0
    for product in list_products():
        if not product["product_name"]:
            continue
        overlap = len(_significant_words(product["product_name"]) & detected_words)
        if overlap > best_score or (overlap == best_score and overlap > 0 and best and len(product["product_name"]) > len(best["product_name"])):
            best, best_score = product, overlap
    return best if best_score > 0 else None


def _vector_literal(embedding: list[float]) -> str:
    """Formats an embedding as the Oracle VECTOR literal string TO_VECTOR()
    accepts: '[v1,v2,...]'."""
    return "[" + ",".join(repr(float(v)) for v in embedding) + "]"


def set_product_reference_embedding(product_id: int, embedding: list[float]) -> None:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE products
            SET reference_image_embedding = TO_VECTOR(:embedding_str, 1536, FLOAT32)
            WHERE product_id = :product_id
            """,
            embedding_str=_vector_literal(embedding),
            product_id=product_id,
        )
        conn.commit()


def has_any_reference_embedding() -> bool:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM products
            WHERE reference_image_embedding IS NOT NULL
            FETCH FIRST 1 ROW ONLY
            """
        )
        return cursor.fetchone() is not None


def match_product_by_image(embedding: list[float], max_distance: float = 0.3) -> dict | None:
    """Best-effort catalog match by reference-image visual similarity
    (cosine distance over Cohere Embed v4 embeddings), per PRD section 2C's
    "configurable recognition without requiring ... retrain[ing]" goal.

    `max_distance` is a heuristic threshold, not an empirically tuned one --
    it was only exercised against a single test image during technical
    verification, not multiple real catalog products, so it will likely need
    tuning once there's real catalog data.

    Only products with a reference image uploaded (REFERENCE_IMAGE_EMBEDDING
    IS NOT NULL) are considered; returns the closest match as a dict, or
    None if the closest match's distance exceeds `max_distance`.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT product_id, product_name, supplier, sku, material, unit_cost,
                   VECTOR_DISTANCE(reference_image_embedding, TO_VECTOR(:embedding_str, 1536, FLOAT32), COSINE) AS distance
            FROM products
            WHERE reference_image_embedding IS NOT NULL
            ORDER BY distance
            FETCH FIRST 1 ROW ONLY
            """,
            embedding_str=_vector_literal(embedding),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        cols = [d[0].lower() for d in cursor.description]
        result = dict(zip(cols, row))
        if result["distance"] > max_distance:
            return None
        return result


# ---------------------------------------------------------------------------
# Disposal events (WASTE_EVENTS)
# ---------------------------------------------------------------------------

def _resolve_bin_id(cursor, location) -> int | None:
    """The physical can an event belongs to, from the free-text LOCATION the
    device reported.

    A capture's LOCATION is matched against CANS.CAN_CODE, which is how the
    seeded fleet's own events are attributed. A live camera rig reports a rig
    name rather than a can code, so LIVE_CAMERA_CAN_CODE names the can it
    feeds; it is only consulted when LOCATION itself resolves to nothing.
    Returns None when neither resolves, which leaves BIN_ID NULL rather than
    attributing items to a can that did not receive them.
    """
    candidates = [location, os.environ.get("LIVE_CAMERA_CAN_CODE")]
    for candidate in candidates:
        if not candidate or not str(candidate).strip():
            continue
        cursor.execute(
            "SELECT can_id FROM cans WHERE can_code = :can_code",
            can_code=str(candidate).strip(),
        )
        row = cursor.fetchone()
        if row is not None:
            return row[0]
    return None


def insert_waste_event(
    detected_object=None,
    material=None,
    category=None,
    location=None,
    confidence=None,
    image_key=None,
    product_id=None,
    created_at=None,
    hazard_flag=None,
    hazard_reason=None,
    visible_text=None,
    reusable_condition=None,
    bin_id=None,
) -> int:
    """bin_id, when given, is the physical can the item was deposited in
    (CANS.can_id). When it is not given it is resolved from `location` (see
    _resolve_bin_id), so a caller does not have to know which can it is
    feeding; it stays NULL for a capture that cannot be attributed to a
    registered unit, which is why the column is nullable.

    created_at, when given, is the actual capture/disposal time (e.g. from an
    edge device queued during a network outage) rather than persist time; it is
    passed straight through as a bind value, so SYSTIMESTAMP is only used when
    the caller has no capture-time timestamp to report."""
    created_at_sql = ":created_at" if created_at is not None else "SYSTIMESTAMP"
    with get_connection() as conn, conn.cursor() as cursor:
        if bin_id is None:
            bin_id = _resolve_bin_id(cursor, location)
        event_id_var = cursor.var(int)
        cursor.execute(
            f"""
            INSERT INTO waste_events
                (product_id, detected_object, material, category, location, confidence, image_key, created_at,
                 hazard_flag, hazard_reason, visible_text, reusable_condition, bin_id)
            VALUES
                (:product_id, :detected_object, :material, :category, :location, :confidence, :image_key, {created_at_sql},
                 :hazard_flag, :hazard_reason, :visible_text, :reusable_condition, :bin_id)
            RETURNING event_id INTO :event_id
            """,
            product_id=product_id,
            detected_object=detected_object,
            material=material,
            category=category,
            location=location,
            confidence=confidence,
            image_key=image_key,
            event_id=event_id_var,
            hazard_flag=hazard_flag,
            hazard_reason=hazard_reason,
            visible_text=visible_text,
            reusable_condition=reusable_condition,
            bin_id=bin_id,
            **({"created_at": created_at} if created_at is not None else {}),
        )
        conn.commit()
        return event_id_var.getvalue()[0]


def list_recent_events(limit: int = 20) -> list[dict]:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT event_id, detected_object, material, category, location, confidence, image_key, created_at,
                   hazard_flag, hazard_reason, visible_text, reusable_condition
            FROM waste_events
            ORDER BY created_at DESC
            FETCH FIRST :limit ROWS ONLY
            """,
            limit=limit,
        )
        cols = [d[0].lower() for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        for row in rows:
            if row["created_at"]:
                row["created_at"] = row["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        return rows


# ---------------------------------------------------------------------------
# Dashboard queries (Experience 4)
# ---------------------------------------------------------------------------

def stats_overview(days: int = 30) -> dict:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM waste_events WHERE created_at >= SYSTIMESTAMP - :days",
            days=days,
        )
        total = cursor.fetchone()[0]

        cursor.execute(
            """
            SELECT category, COUNT(*) AS n
            FROM waste_events
            WHERE created_at >= SYSTIMESTAMP - :days
            GROUP BY category
            ORDER BY n DESC
            """,
            days=days,
        )
        by_category = [{"category": r[0] or "unknown", "count": r[1]} for r in cursor.fetchall()]

        cursor.execute(
            """
            SELECT detected_object, COUNT(*) AS n
            FROM waste_events
            WHERE created_at >= SYSTIMESTAMP - :days AND detected_object IS NOT NULL
            GROUP BY detected_object
            ORDER BY n DESC
            FETCH FIRST 10 ROWS ONLY
            """,
            days=days,
        )
        top_items = [{"object": r[0], "count": r[1]} for r in cursor.fetchall()]

        cursor.execute(
            """
            SELECT TRUNC(created_at) AS day, COUNT(*) AS n
            FROM waste_events
            WHERE created_at >= SYSTIMESTAMP - :days
            GROUP BY TRUNC(created_at)
            ORDER BY day
            """,
            days=days,
        )
        trend = [{"date": r[0].strftime("%Y-%m-%d"), "count": r[1]} for r in cursor.fetchall()]

        return {
            "window_days": days,
            "total_items": total,
            "by_category": by_category,
            "top_items": top_items,
            "trend": trend,
        }


def stats_items(days: int = 30) -> list[dict]:
    """Item-level intelligence: per-item counts, joined to catalog price where matched."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                we.detected_object,
                p.product_name,
                COUNT(*) AS n,
                MAX(we.created_at) AS last_seen,
                p.unit_cost
            FROM waste_events we
            LEFT JOIN products p ON p.product_id = we.product_id
            WHERE we.created_at >= SYSTIMESTAMP - :days AND we.detected_object IS NOT NULL
            GROUP BY we.detected_object, p.product_name, p.unit_cost
            ORDER BY n DESC
            """,
            days=days,
        )
        rows = []
        for detected_object, product_name, count, last_seen, unit_cost in cursor.fetchall():
            estimated_value = float(unit_cost) * count if unit_cost is not None else None
            rows.append({
                "detected_object": detected_object,
                "matched_product": product_name,
                "count": count,
                "last_seen": last_seen.strftime("%Y-%m-%d %H:%M:%S") if last_seen else None,
                "estimated_value": estimated_value,
            })
        return rows


def list_hazard_events(days: int = 30) -> list[dict]:
    """Recent events flagged as a visible hazard (battery/chemical/sharps indicator etc),
    for insights.py's hazard recommendation rule."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT detected_object, location, hazard_reason, created_at
            FROM waste_events
            WHERE hazard_flag = 1 AND created_at >= SYSTIMESTAMP - :days
            ORDER BY created_at DESC
            """,
            days=days,
        )
        rows = [
            {
                "detected_object": r[0],
                "location": r[1] or "unspecified",
                "hazard_reason": r[2],
                "date": r[3].strftime("%Y-%m-%d") if r[3] else None,
            }
            for r in cursor.fetchall()
        ]
        return rows


def stats_locations(days: int = 30) -> list[dict]:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                COALESCE(location, 'unspecified') AS loc,
                category,
                COUNT(*) AS n
            FROM waste_events
            WHERE created_at >= SYSTIMESTAMP - :days
            GROUP BY COALESCE(location, 'unspecified'), category
            ORDER BY loc, n DESC
            """,
            days=days,
        )
        rows = [{"location": r[0], "category": r[1] or "unknown", "count": r[2]} for r in cursor.fetchall()]
        return rows


# ---------------------------------------------------------------------------
# Recommendations (Experience 5)
# ---------------------------------------------------------------------------

def insert_recommendation(text: str) -> int:
    with get_connection() as conn, conn.cursor() as cursor:
        rec_id_var = cursor.var(int)
        cursor.execute(
            """
            INSERT INTO recommendations (recommendation_text, created_at)
            VALUES (:text, SYSTIMESTAMP)
            RETURNING recommendation_id INTO :rec_id
            """,
            text=text,
            rec_id=rec_id_var,
        )
        conn.commit()
        return rec_id_var.getvalue()[0]


def list_recommendations(limit: int = 20) -> list[dict]:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT recommendation_id, recommendation_text, created_at
            FROM recommendations
            ORDER BY created_at DESC
            FETCH FIRST :limit ROWS ONLY
            """,
            limit=limit,
        )
        return [
            {
                "id": r[0],
                "text": r[1].read() if hasattr(r[1], "read") else r[1],
                "created_at": r[2].strftime("%Y-%m-%d %H:%M:%S") if r[2] else None,
            }
            for r in cursor.fetchall()
        ]


# ---------------------------------------------------------------------------
# Campus fleet (CAN_MODELS / BUILDINGS / CANS / CAN_READINGS / SERVICE_EVENTS)
# ---------------------------------------------------------------------------
# Physical-unit inventory behind the campus map. Status and fill are *derived*
# from these rows rather than stored on them -- see fleet.py, which owns that
# derivation; everything here is plain retrieval and insertion.

def list_can_models() -> list[dict]:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT model_id, model_code, display_name, capacity_liters, capacity_items,
                   height_cm, stream_count, has_camera, has_actuator, firmware_version, released_on
            FROM can_models
            ORDER BY capacity_liters DESC, model_code
            """
        )
        cols = [d[0].lower() for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        for row in rows:
            row["released_on"] = row["released_on"].strftime("%Y-%m-%d") if row["released_on"] else None
        return rows


def list_buildings() -> list[dict]:
    """Buildings with their active can count, so the sidebar and filter list can
    show where the fleet actually is."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT b.building_id, b.building_code, b.name, b.campus_area,
                   b.latitude, b.longitude,
                   (SELECT COUNT(*) FROM cans c
                     WHERE c.building_id = b.building_id AND c.lifecycle_status = 'active') AS can_count
            FROM buildings b
            ORDER BY b.name
            """
        )
        cols = [d[0].lower() for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]


# One row per can: stored columns, joined model and building, the latest
# reading flattened on, and the raw inputs fleet.py needs to derive fill
# (events attributed to this can since it was last emptied, and the model's
# item capacity). Non-active cans are excluded -- a removed can is not on the
# map and should not count towards fleet health.
_CAN_ROW_SQL = """
WITH latest_reading AS (
    SELECT r.*,
           ROW_NUMBER() OVER (PARTITION BY r.can_id ORDER BY r.reported_at DESC, r.reading_id DESC) AS rn
    FROM can_readings r
),
last_emptied AS (
    SELECT can_id, MAX(performed_at) AS emptied_at
    FROM service_events
    WHERE service_type = 'emptied'
    GROUP BY can_id
)
SELECT c.can_id, c.can_code, c.floor, c.placement_note,
       c.latitude, c.longitude, c.installed_on, c.lifecycle_status, c.is_simulated,
       m.model_id, m.model_code, m.display_name AS model_name,
       m.capacity_liters, m.capacity_items, m.height_cm, m.stream_count,
       m.has_camera, m.has_actuator, m.firmware_version,
       b.building_id, b.building_code, b.name AS building_name, b.campus_area,
       l.reported_at, l.fill_percent, l.camera_ok, l.actuator_ok, l.connectivity_ok,
       l.battery_percent, l.fault_code, l.fault_detail,
       le.emptied_at AS last_emptied_at,
       (SELECT COUNT(*)
          FROM waste_events we
         WHERE we.bin_id = c.can_id
           AND (le.emptied_at IS NULL OR we.created_at >= le.emptied_at)) AS events_since_emptied
FROM cans c
JOIN can_models m ON m.model_id = c.model_id
JOIN buildings b ON b.building_id = c.building_id
LEFT JOIN latest_reading l ON l.can_id = c.can_id AND l.rn = 1
LEFT JOIN last_emptied le ON le.can_id = c.can_id
WHERE c.lifecycle_status = 'active'
"""


def list_can_rows(
    can_id: int | None = None,
    building_id: int | None = None,
    model_id: int | None = None,
) -> list[dict]:
    """Raw can rows for fleet.py to resolve. Status is deliberately not a filter
    here: it does not exist as a column, so fleet.py filters on it after
    deriving it."""
    clauses = []
    binds: dict = {}
    if can_id is not None:
        clauses.append("AND c.can_id = :can_id")
        binds["can_id"] = can_id
    if building_id is not None:
        clauses.append("AND c.building_id = :building_id")
        binds["building_id"] = building_id
    if model_id is not None:
        clauses.append("AND c.model_id = :model_id")
        binds["model_id"] = model_id

    sql = _CAN_ROW_SQL + "\n".join(clauses) + "\nORDER BY b.name, c.can_code"
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(sql, **binds)
        cols = [d[0].lower() for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        for row in rows:
            row["installed_on"] = row["installed_on"].strftime("%Y-%m-%d") if row["installed_on"] else None
            for key in ("latitude", "longitude", "capacity_liters", "height_cm", "battery_percent"):
                if row[key] is not None:
                    row[key] = float(row[key])
        return rows


def list_can_readings(can_id: int, limit: int = 200) -> list[dict]:
    """Newest-first telemetry tail for one can."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT reading_id, reported_at, fill_percent, fill_source, camera_ok, actuator_ok,
                   connectivity_ok, battery_percent, fault_code, fault_detail
            FROM can_readings
            WHERE can_id = :can_id
            ORDER BY reported_at DESC, reading_id DESC
            FETCH FIRST :limit ROWS ONLY
            """,
            can_id=can_id,
            limit=limit,
        )
        cols = [d[0].lower() for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        for row in rows:
            row["reported_at"] = row["reported_at"].strftime("%Y-%m-%d %H:%M:%S") if row["reported_at"] else None
            for key in ("fill_percent", "battery_percent"):
                if row[key] is not None:
                    row[key] = float(row[key])
        return rows


def list_service_events(can_id: int, limit: int = 20) -> list[dict]:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT service_id, service_type, performed_at, performed_by, notes
            FROM service_events
            WHERE can_id = :can_id
            ORDER BY performed_at DESC, service_id DESC
            FETCH FIRST :limit ROWS ONLY
            """,
            can_id=can_id,
            limit=limit,
        )
        cols = [d[0].lower() for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        for row in rows:
            row["performed_at"] = row["performed_at"].strftime("%Y-%m-%d %H:%M:%S") if row["performed_at"] else None
        return rows


def insert_service_event(can_id: int, service_type: str, performed_by=None, notes=None) -> int:
    with get_connection() as conn, conn.cursor() as cursor:
        service_id_var = cursor.var(int)
        cursor.execute(
            """
            INSERT INTO service_events (can_id, service_type, performed_at, performed_by, notes)
            VALUES (:can_id, :service_type, SYSTIMESTAMP, :performed_by, :notes)
            RETURNING service_id INTO :service_id
            """,
            can_id=can_id,
            service_type=service_type,
            performed_by=performed_by,
            notes=notes,
            service_id=service_id_var,
        )
        conn.commit()
        return service_id_var.getvalue()[0]


def can_contents(can_id: int, days: int = 30, event_limit: int = 50) -> dict:
    """What one can contains: the category split, the items seen most often, the
    estimated catalog value of what was thrown away, and the recent events
    themselves.

    Scoped to disposals since the can was last emptied where that is known, so
    "contains" means what is in it now rather than everything it has ever seen;
    falls back to the `days` window for a can with no emptying on record.
    The estimated_value join mirrors stats_items -- catalog cost times count,
    only for events matched to a PRODUCTS row.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT MAX(performed_at) FROM service_events
            WHERE can_id = :can_id AND service_type = 'emptied'
            """,
            can_id=can_id,
        )
        last_emptied = cursor.fetchone()[0]

        if last_emptied is not None:
            window_sql = "we.created_at >= :since"
            binds = {"can_id": can_id, "since": last_emptied}
        else:
            window_sql = "we.created_at >= SYSTIMESTAMP - :days"
            binds = {"can_id": can_id, "days": days}

        cursor.execute(
            f"""
            SELECT COALESCE(we.category, 'unknown') AS category, COUNT(*) AS n
            FROM waste_events we
            WHERE we.bin_id = :can_id AND {window_sql}
            GROUP BY COALESCE(we.category, 'unknown')
            ORDER BY n DESC
            """,
            **binds,
        )
        by_category = [{"category": r[0], "count": r[1]} for r in cursor.fetchall()]

        cursor.execute(
            f"""
            SELECT we.detected_object, p.product_name, COUNT(*) AS n, p.unit_cost
            FROM waste_events we
            LEFT JOIN products p ON p.product_id = we.product_id
            WHERE we.bin_id = :can_id AND {window_sql} AND we.detected_object IS NOT NULL
            GROUP BY we.detected_object, p.product_name, p.unit_cost
            ORDER BY n DESC
            FETCH FIRST 10 ROWS ONLY
            """,
            **binds,
        )
        top_items = []
        for detected_object, product_name, count, unit_cost in cursor.fetchall():
            top_items.append({
                "detected_object": detected_object,
                "matched_product": product_name,
                "count": count,
                "estimated_value": float(unit_cost) * count if unit_cost is not None else None,
            })

        cursor.execute(
            f"""
            SELECT SUM(p.unit_cost)
            FROM waste_events we
            JOIN products p ON p.product_id = we.product_id
            WHERE we.bin_id = :can_id AND {window_sql}
            """,
            **binds,
        )
        total_value_row = cursor.fetchone()[0]

        cursor.execute(
            f"""
            SELECT we.event_id, we.detected_object, we.material, we.category, we.location,
                   we.confidence, we.image_key, we.created_at, we.hazard_flag, we.hazard_reason,
                   we.visible_text, we.reusable_condition
            FROM waste_events we
            WHERE we.bin_id = :can_id AND {window_sql}
            ORDER BY we.created_at DESC
            FETCH FIRST :event_limit ROWS ONLY
            """,
            **binds,
            event_limit=event_limit,
        )
        cols = [d[0].lower() for d in cursor.description]
        events = [dict(zip(cols, row)) for row in cursor.fetchall()]
        for event in events:
            if event["created_at"]:
                event["created_at"] = event["created_at"].strftime("%Y-%m-%d %H:%M:%S")

        return {
            "can_id": can_id,
            "since": last_emptied.strftime("%Y-%m-%d %H:%M:%S") if last_emptied else None,
            "window_days": None if last_emptied else days,
            "total_items": sum(row["count"] for row in by_category),
            "by_category": by_category,
            "top_items": top_items,
            "estimated_value": float(total_value_row) if total_value_row is not None else None,
            "events": events,
        }


# --- Fleet inventory upserts (used by seed_campus.py; keyed on the natural
# --- business codes so re-running inserts nothing a second time) -------------

def _upsert(table: str, key_column: str, key_value, columns: dict, pk_column: str) -> int:
    """Insert-or-skip on a natural key, returning the row's primary key.

    Oracle's MERGE would work here, but these tables use GENERATED ALWAYS AS
    IDENTITY keys and the seed needs the resulting id either way, so a lookup
    followed by a RETURNING insert is both shorter and easier to read than a
    MERGE plus a second SELECT. Nothing is ever updated: an existing row is
    left exactly as it is, which is what makes the seed safe to re-run against
    a database someone has since edited by hand.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            f"SELECT {pk_column} FROM {table} WHERE {key_column} = :key_value",
            key_value=key_value,
        )
        row = cursor.fetchone()
        if row is not None:
            return row[0]

        names = [key_column, *columns.keys()]
        binds = {key_column: key_value, **columns}
        placeholders = ", ".join(f":{name}" for name in names)
        pk_var = cursor.var(int)
        cursor.execute(
            f"""
            INSERT INTO {table} ({", ".join(names)})
            VALUES ({placeholders})
            RETURNING {pk_column} INTO :pk_out
            """,
            **binds,
            pk_out=pk_var,
        )
        conn.commit()
        return pk_var.getvalue()[0]


def upsert_can_model(model_code: str, **columns) -> int:
    return _upsert("can_models", "model_code", model_code, columns, "model_id")


def upsert_building(building_code: str, **columns) -> int:
    return _upsert("buildings", "building_code", building_code, columns, "building_id")


def upsert_can(can_code: str, **columns) -> int:
    return _upsert("cans", "can_code", can_code, columns, "can_id")


def count_rows_by_can(table: str) -> dict[int, int]:
    """Row counts per can_id for an append-only fleet table.

    The seed uses this to decide which cans still need a telemetry tail or a
    service history: a can that already has rows is left untouched rather than
    accumulating a duplicate tail on every re-run.
    """
    if table not in ("can_readings", "service_events"):
        raise ValueError(f"Unsupported table for per-can counts: {table!r}")
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(f"SELECT can_id, COUNT(*) FROM {table} GROUP BY can_id")
        return {row[0]: row[1] for row in cursor.fetchall()}


def count_waste_events_by_can() -> dict[int, int]:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT bin_id, COUNT(*) FROM waste_events WHERE bin_id IS NOT NULL GROUP BY bin_id"
        )
        return {row[0]: row[1] for row in cursor.fetchall()}


def backfill_waste_event_bin_ids(location_to_can_code: dict[str, str]) -> dict[str, int]:
    """Attributes already-logged events to a can where their free-text LOCATION
    clearly corresponds to one.

    LOCATION is deliberately left in place as the raw value the device
    reported; BIN_ID is the resolved physical unit alongside it. Only rows
    with BIN_ID still NULL are touched, so a hand-corrected attribution is
    never overwritten. Returns rows updated per location.
    """
    updated = {}
    with get_connection() as conn, conn.cursor() as cursor:
        for location, can_code in location_to_can_code.items():
            cursor.execute(
                """
                UPDATE waste_events
                SET bin_id = (SELECT can_id FROM cans WHERE can_code = :can_code)
                WHERE location = :location
                  AND bin_id IS NULL
                  AND EXISTS (SELECT 1 FROM cans WHERE can_code = :can_code)
                """,
                can_code=can_code,
                location=location,
            )
            updated[location] = cursor.rowcount
        conn.commit()
    return updated
