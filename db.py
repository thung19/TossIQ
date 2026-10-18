"""OCI Autonomous DB access layer for TossIQ.

All disposal-event persistence, catalog (PRODUCTS) lookups, and
recommendation storage go through here. Kept deliberately thin: plain
SQL over python-oracledb, no ORM, since the schema is small and already
fixed in OCI (WASTE_EVENTS / PRODUCTS / RECOMMENDATIONS).

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
) -> int:
    """created_at, when given, is the actual capture/disposal time (e.g. from an
    edge device queued during a network outage) rather than persist time; it is
    passed straight through as a bind value, so SYSTIMESTAMP is only used when
    the caller has no capture-time timestamp to report."""
    created_at_sql = ":created_at" if created_at is not None else "SYSTIMESTAMP"
    with get_connection() as conn, conn.cursor() as cursor:
        event_id_var = cursor.var(int)
        cursor.execute(
            f"""
            INSERT INTO waste_events
                (product_id, detected_object, material, category, location, confidence, image_key, created_at,
                 hazard_flag, hazard_reason, visible_text, reusable_condition)
            VALUES
                (:product_id, :detected_object, :material, :category, :location, :confidence, :image_key, {created_at_sql},
                 :hazard_flag, :hazard_reason, :visible_text, :reusable_condition)
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


VALID_HAZARD_STATUSES = ("open", "acknowledged", "resolved")


def list_hazard_events(days: int = 30) -> list[dict]:
    """Recent events flagged as a visible hazard (battery/chemical/sharps indicator etc),
    for insights.py's hazard recommendation rule and the Hazard Detection dashboard page."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT event_id, detected_object, location, hazard_reason, created_at, image_key, hazard_status
            FROM waste_events
            WHERE hazard_flag = 1 AND created_at >= SYSTIMESTAMP - :days
            ORDER BY created_at DESC
            """,
            days=days,
        )
        rows = [
            {
                "event_id": r[0],
                "detected_object": r[1],
                "location": r[2] or "unspecified",
                "hazard_reason": r[3],
                "date": r[4].strftime("%Y-%m-%d") if r[4] else None,
                "image_key": r[5],
                "hazard_status": r[6],
            }
            for r in cursor.fetchall()
        ]
        return rows


def update_hazard_status(event_id: int, status: str) -> None:
    """Advances a hazard-flagged event's review status (open -> acknowledged ->
    resolved), per PRD section 2F's "preliminary flags requiring human review".

    Raises ValueError for an invalid status (the API layer turns that into a 400)
    and LookupError when event_id doesn't exist or isn't hazard-flagged (the API
    layer turns that into a 404)."""
    if status not in VALID_HAZARD_STATUSES:
        raise ValueError(
            f"Invalid hazard status {status!r}; expected one of {VALID_HAZARD_STATUSES}"
        )
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "UPDATE waste_events SET hazard_status = :status WHERE event_id = :event_id AND hazard_flag = 1",
            status=status,
            event_id=event_id,
        )
        if cursor.rowcount == 0:
            raise LookupError(f"No hazard-flagged event with event_id {event_id}")
        conn.commit()


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
