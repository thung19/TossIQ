"""OCI Autonomous DB access layer for TossIQ.

All disposal-event persistence, catalog (PRODUCTS) lookups, recommendation
storage, and campus-fleet inventory queries go through here. Kept deliberately
thin: plain SQL over python-oracledb, no ORM, since the schema is small.

WASTE_EVENTS / PRODUCTS / RECOMMENDATIONS predate this repository tracking its
own DDL and exist in OCI without tracked definitions. The campus-fleet tables
(CAN_MODELS / BUILDINGS / CANS / CAN_READINGS / SERVICE_EVENTS, and
WASTE_EVENTS.BIN_ID) are defined in schema/ and applied by schema/apply.py.

Connections come from a pool. They used to be opened per call, which the
previous version of this docstring described as "the simplest thing that
works" with a note to swap in a pool if it became a bottleneck. It did:
opening a connection to this ADB costs ~0.29 s against ~0.09 s for the
query it then runs, so a page issuing eight aggregates spent three quarters
of its time on handshakes. GET /initiatives, which measures every goal
against live data, took four seconds; pooled it takes well under one.

The pool is created lazily on first use and shared process-wide. If it
cannot be created -- a wallet problem, a version of oracledb without
pooling -- get_connection falls back to a direct connect rather than
failing, because a slow dashboard is better than a broken one.
"""

import os
import threading
from contextlib import contextmanager

import oracledb
from dotenv import load_dotenv

load_dotenv()

# Small on purpose. This is one API process serving a dashboard, not a
# fleet of workers, and an Autonomous DB's own session limits are the thing
# to stay well inside.
POOL_MIN = int(os.environ.get("DB_POOL_MIN") or "1")
POOL_MAX = int(os.environ.get("DB_POOL_MAX") or "8")

_pool = None
_pool_lock = threading.Lock()
_pool_failed = False


def _connect_kwargs() -> dict:
    wallet_dir = os.environ["DB_WALLET_DIR"]
    return {
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "dsn": os.environ["DB_DSN"],
        "config_dir": wallet_dir,
        "wallet_location": wallet_dir,
        "wallet_password": os.environ["DB_WALLET_PASSWORD"],
    }


def _get_pool():
    """The shared pool, created on first use.

    Double-checked under a lock because the camera service persists
    detections from its own thread while the API serves requests, so first
    use is genuinely concurrent.
    """
    global _pool, _pool_failed
    if _pool is not None or _pool_failed:
        return _pool
    with _pool_lock:
        if _pool is not None or _pool_failed:
            return _pool
        try:
            _pool = oracledb.create_pool(
                min=POOL_MIN,
                max=POOL_MAX,
                increment=1,
                # Hand back a connection that has gone stale rather than
                # letting a caller discover it mid-query.
                ping_interval=60,
                getmode=oracledb.POOL_GETMODE_WAIT,
                **_connect_kwargs(),
            )
        except Exception:
            # Falling back rather than raising: a slow dashboard beats a
            # broken one, and the cause belongs in the log, not in a 500.
            _pool_failed = True
            _pool = None
    return _pool


@contextmanager
def get_connection():
    """A connection, pooled where possible.

    `.close()` on a pooled connection returns it to the pool rather than
    tearing it down, so every existing caller keeps working unchanged.
    """
    pool = _get_pool()
    connection = pool.acquire() if pool is not None else oracledb.connect(**_connect_kwargs())
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
    """The full catalog row, including the cost/mass/variant detail schema 002
    added. UNIT_WEIGHT_GRAMS is a catalog reference mass, never a measurement
    -- no can has a weight sensor."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT product_id, product_name, brand, variant_label, supplier, sku,
                   detected_as, material, material_subtype, unit_cost,
                   unit_weight_grams, disposal_category, recyclable, reusable,
                   case_pack_qty, case_cost, active,
                   substitute_sku, substitute_note, substitute_kind, expected_uses
            FROM products
            ORDER BY product_name
            """
        )
        cols = [d[0].lower() for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        for row in rows:
            for key in ("unit_cost", "unit_weight_grams", "case_cost"):
                if row[key] is not None:
                    row[key] = float(row[key])
        return rows


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

def _can_id_for_code(cursor, can_code) -> int | None:
    """The CANS row for a can code, or None when the code is empty or names no
    registered can.

    A can must never be credited with items that were not put in it, so this
    is an exact match on CAN_CODE and nothing else: there is no fallback can.
    """
    if not can_code or not str(can_code).strip():
        return None
    cursor.execute(
        "SELECT can_id FROM cans WHERE can_code = :can_code",
        can_code=str(can_code).strip(),
    )
    row = cursor.fetchone()
    return row[0] if row is not None else None


def can_id_for_code(can_code) -> int | None:
    """can_id for a can code, for a caller that knows which can it is feeding
    but only by code (see camera_service.py). None when the code names no
    registered can."""
    with get_connection() as conn, conn.cursor() as cursor:
        return _can_id_for_code(cursor, can_code)


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
    hazard_class=None,
    hazard_severity=None,
) -> int:
    """bin_id, when given, is the physical can the item was deposited in
    (CANS.can_id). When it is not given it is resolved by matching `location`
    against CANS.CAN_CODE, which is how the seeded fleet's own events are
    attributed; a capture whose location is empty or names no registered can
    stays NULL rather than being credited to some other can, which is why the
    column is nullable.

    created_at, when given, is the actual capture/disposal time (e.g. from an
    edge device queued during a network outage) rather than persist time; it is
    passed straight through as a bind value, so SYSTIMESTAMP is only used when
    the caller has no capture-time timestamp to report."""
    created_at_sql = ":created_at" if created_at is not None else "SYSTIMESTAMP"
    with get_connection() as conn, conn.cursor() as cursor:
        if bin_id is None:
            bin_id = _can_id_for_code(cursor, location)
        event_id_var = cursor.var(int)
        cursor.execute(
            f"""
            INSERT INTO waste_events
                (product_id, detected_object, material, category, location, confidence, image_key, created_at,
                 hazard_flag, hazard_reason, visible_text, reusable_condition, bin_id,
                 hazard_class, hazard_severity)
            VALUES
                (:product_id, :detected_object, :material, :category, :location, :confidence, :image_key, {created_at_sql},
                 :hazard_flag, :hazard_reason, :visible_text, :reusable_condition, :bin_id,
                 :hazard_class, :hazard_severity)
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
            hazard_class=hazard_class,
            hazard_severity=hazard_severity,
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
# Catalog detail and review trail (used by seed_catalog.py and analytics.py)
# ---------------------------------------------------------------------------

def product_id_for_sku(sku: str) -> int | None:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT product_id FROM products WHERE sku = :sku", sku=sku)
        row = cursor.fetchone()
        return row[0] if row else None


def upsert_product_by_sku(sku: str, **columns) -> int:
    """Insert-or-skip on SKU, returning the product_id.

    Mirrors _upsert's contract for the fleet tables: an existing row is left
    untouched, so a price someone corrected by hand survives a re-seed.
    """
    return _upsert("products", "sku", sku, columns, "product_id")



def fill_null_product_columns(sku: str, columns: dict) -> int:
    """Sets the given columns on one product, but only where they are NULL.

    "Only where NULL" is the whole point: this completes a row that predates
    a schema change without overwriting anything a person has since put
    there. Returns the number of columns actually written.
    """
    if not columns:
        return 0
    allowed = {
        "brand", "variant_label", "detected_as", "material", "material_subtype",
        "unit_cost", "unit_weight_grams", "disposal_category", "recyclable",
        "reusable", "case_pack_qty", "case_cost", "active",
        "substitute_sku", "substitute_note", "substitute_kind", "expected_uses",
    }
    unknown = set(columns) - allowed
    if unknown:
        raise ValueError(f"Not product columns: {sorted(unknown)}")

    assignments = ", ".join(f"{name} = COALESCE({name}, :{name})" for name in columns)
    predicate = " OR ".join(f"{name} IS NULL" for name in columns)
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            f"UPDATE products SET {assignments} WHERE sku = :sku AND ({predicate})",
            sku=sku,
            **columns,
        )
        written = cursor.rowcount and len(columns)
        conn.commit()
        return written or 0


def list_unattributed_events() -> list[tuple]:
    """(event_id, detected_object) for every event with no PRODUCT_ID yet."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT event_id, detected_object
            FROM waste_events
            WHERE product_id IS NULL
            ORDER BY event_id
            """
        )
        return cursor.fetchall()


def set_event_product_matches(updates: list[dict]) -> int:
    """Batch-applies {event_id, product_id, match_method} attributions.

    One executemany rather than db.py's usual connection-per-call, because
    the only caller is a seed with a few thousand rows to write and a
    per-row connection would cost minutes against OCI (same reasoning as
    seed_campus._insert_batch).
    """
    if not updates:
        return 0
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.executemany(
            """
            UPDATE waste_events
               SET product_id = :product_id, match_method = :match_method
             WHERE event_id = :event_id
            """,
            updates,
        )
        conn.commit()
    return len(updates)



def normalize_confidence_scale() -> int:
    """Rescales CONFIDENCE values stored on a 0-1 scale to the 0-100 the
    column is documented to hold.

    Two writers disagreed: camera_service.py persisted the detector's raw
    0-1 score while api.py's advanced path wrote 0-100 (see its
    CONFIDENCE_FULL constants), so any average over the column mixed units
    and every accuracy figure derived from it was wrong. camera_service.py
    now scales on write; this repairs the rows written before it did.

    A value of exactly 1.0 is ambiguous -- it could be a certain 0-1 score or
    a 1% confidence -- and is left alone rather than guessed at. In practice
    neither writer emits it: the detector clamps below 1.0 and the advanced
    path's lowest constant is 20.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE waste_events
               SET confidence = ROUND(confidence * 100, 2)
             WHERE confidence IS NOT NULL AND confidence < 1
            """
        )
        updated = cursor.rowcount
        conn.commit()
        return updated


def list_unreviewed_events() -> list[tuple]:
    """(event_id, detected_object, category, confidence, created_at) for events
    nobody has reviewed yet."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT we.event_id, we.detected_object, we.category, we.confidence, we.created_at
            FROM waste_events we
            WHERE NOT EXISTS (
                SELECT 1 FROM event_reviews r WHERE r.event_id = we.event_id
            )
            ORDER BY we.event_id
            """
        )
        return cursor.fetchall()


def insert_event_reviews(rows: list[dict]) -> int:
    if not rows:
        return 0
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO event_reviews
                (event_id, verdict, corrected_category, corrected_object, reviewer, reviewed_at, notes)
            VALUES
                (:event_id, :verdict, :corrected_category, :corrected_object, :reviewer, :reviewed_at, :notes)
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def count_event_reviews() -> int:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM event_reviews")
        return cursor.fetchone()[0]


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
# Analytics queries (the analytics page)
# ---------------------------------------------------------------------------
# One join shape serves every question the page asks, so a filter written once
# applies to all of them: a disposal event, the catalog product it was matched
# to, and the can and building it was thrown into.
#
# LABEL_AVG is what makes a cost or mass figure available for an event that
# was never matched to a specific product. The catalog knows what a "plastic
# water bottle" costs on average even when it cannot say which bottle this
# was, and reporting that average -- flagged as a class estimate rather than a
# product match -- is more useful than reporting nothing. Events whose label
# the catalog does not cover at all contribute to neither total and are
# counted separately, so the unknown share is always visible.

_ANALYTICS_FROM = """
FROM waste_events we
LEFT JOIN products p  ON p.product_id = we.product_id
LEFT JOIN cans c      ON c.can_id = we.bin_id
LEFT JOIN buildings b ON b.building_id = c.building_id
LEFT JOIN label_avg la ON la.detected_as = we.detected_object
"""

_LABEL_AVG_CTE = """
WITH label_avg AS (
    SELECT detected_as,
           AVG(unit_cost) AS avg_cost,
           AVG(unit_weight_grams) AS avg_grams
    FROM products
    WHERE active = 1 AND detected_as IS NOT NULL
    GROUP BY detected_as
)
"""

# The measure columns every grouped analytics query selects. Kept in one place
# so a cost total means the same thing on every tab of the page.
_ANALYTICS_MEASURES = """
    COUNT(*) AS n,
    COUNT(we.product_id) AS matched_n,
    SUM(CASE WHEN p.unit_cost IS NOT NULL THEN p.unit_cost ELSE 0 END) AS matched_cost,
    SUM(CASE WHEN p.unit_weight_grams IS NOT NULL THEN p.unit_weight_grams ELSE 0 END) AS matched_grams,
    SUM(CASE WHEN p.unit_cost IS NULL AND la.avg_cost IS NOT NULL THEN la.avg_cost ELSE 0 END) AS class_cost,
    SUM(CASE WHEN p.unit_weight_grams IS NULL AND la.avg_grams IS NOT NULL THEN la.avg_grams ELSE 0 END) AS class_grams,
    SUM(CASE WHEN COALESCE(p.unit_cost, la.avg_cost) IS NULL THEN 1 ELSE 0 END) AS no_cost_n,
    SUM(CASE WHEN we.hazard_flag = 1 THEN 1 ELSE 0 END) AS hazard_n,
    SUM(CASE WHEN we.hazard_flag = 1 AND we.hazard_severity = 'critical' THEN 1 ELSE 0 END)
        AS hazard_critical_n,
    AVG(we.confidence) AS avg_confidence
"""

# Whitelisted grouping expressions. The dimension arrives from the query
# string, so it selects a key from this map and is never interpolated -- an
# unknown dimension raises rather than reaching the SQL.
ANALYTICS_DIMENSIONS = {
    "category":         "COALESCE(we.category, 'unknown')",
    "material":         "COALESCE(p.material, we.material, 'unknown')",
    "material_subtype": "COALESCE(p.material_subtype, we.material_subtype, 'unspecified')",
    "object":           "COALESCE(we.detected_object, 'unidentified')",
    "product":          "COALESCE(p.product_name, 'no catalog match')",
    # TRIM matters: Oracle concatenates NULL as empty, so a product with no
    # brand or variant would bucket as a bare space rather than falling
    # through to its name. An empty string is NULL in Oracle, so the TRIM
    # lets COALESCE do its job.
    "variant":          "COALESCE(TRIM(p.brand || ' ' || p.variant_label), p.product_name, 'no catalog match')",
    "brand":            "COALESCE(p.brand, 'unbranded or unmatched')",
    "supplier":         "COALESCE(p.supplier, 'unknown supplier')",
    "sku":              "COALESCE(p.sku, 'unmatched')",
    "building":         "COALESCE(b.name, 'unattributed')",
    "campus_area":      "COALESCE(b.campus_area, 'unattributed')",
    "can":              "COALESCE(c.can_code, 'unattributed')",
    "floor":            "COALESCE(c.floor, 'unspecified')",
    "correct_bin":      "COALESCE(p.disposal_category, 'unknown')",
    "match_method":     "COALESCE(we.match_method, 'unmatched')",
    # Non-hazards bucket as 'not hazardous' rather than being excluded, so
    # the hazard slice is always readable against the whole population
    # instead of looking like the only thing on campus.
    "hazard_class":     "CASE WHEN we.hazard_flag = 1 "
                        "THEN COALESCE(we.hazard_class, 'unclassified') "
                        "ELSE 'not hazardous' END",
    "hazard_severity":  "CASE WHEN we.hazard_flag = 1 "
                        "THEN COALESCE(we.hazard_severity, 'unclassified') "
                        "ELSE 'not hazardous' END",
    "hour":             "TO_CHAR(we.created_at, 'HH24')",
    "weekday":          "TO_CHAR(TRUNC(we.created_at) - TRUNC(we.created_at, 'IW'))",
    "day":              "TO_CHAR(we.created_at, 'YYYY-MM-DD')",
}

# Dimensions whose natural order is their own, not their size. A date series
# sorted by volume is not a time series -- it is a leaderboard with dates for
# labels, and reading a trend off it is impossible. The string forms above are
# all zero-padded so a lexical sort is also the chronological one.
ORDERED_DIMENSIONS = {"hour", "weekday", "day"}


def _analytics_filters(
    days: int | None,
    building_id: int | None,
    can_id: int | None,
    category: str | None,
    material: str | None,
    detected_object: str | None,
    supplier: str | None,
) -> tuple[str, dict]:
    """Builds the shared WHERE fragment and its bind values.

    Every clause is a bind, never interpolated text, so a filter value that
    happens to contain a quote is data rather than SQL.
    """
    clauses = []
    binds: dict = {}
    if days is not None:
        clauses.append("we.created_at >= SYSTIMESTAMP - :days")
        binds["days"] = days
    if building_id is not None:
        clauses.append("c.building_id = :building_id")
        binds["building_id"] = building_id
    if can_id is not None:
        clauses.append("we.bin_id = :can_id")
        binds["can_id"] = can_id
    if category:
        clauses.append("we.category = :category")
        binds["category"] = category
    if material:
        clauses.append("COALESCE(p.material, we.material) = :material")
        binds["material"] = material
    if detected_object:
        clauses.append("we.detected_object = :detected_object")
        binds["detected_object"] = detected_object
    if supplier:
        clauses.append("p.supplier = :supplier")
        binds["supplier"] = supplier
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, binds


def analytics_distribution(
    dimension: str,
    days: int | None = 30,
    building_id: int | None = None,
    can_id: int | None = None,
    category: str | None = None,
    material: str | None = None,
    detected_object: str | None = None,
    supplier: str | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Counts, costs and masses grouped by one whitelisted dimension.

    This single query backs every "distribution of X" view on the analytics
    page. Serving them from one shaped query rather than a handful of
    bespoke ones is what keeps the cost column on the supplier tab equal to
    the cost column on the material tab for the same filters.
    """
    if dimension not in ANALYTICS_DIMENSIONS:
        raise ValueError(
            f"Unknown dimension {dimension!r}; expected one of {sorted(ANALYTICS_DIMENSIONS)}"
        )
    expression = ANALYTICS_DIMENSIONS[dimension]
    where, binds = _analytics_filters(
        days, building_id, can_id, category, material, detected_object, supplier
    )

    sql = f"""
        {_LABEL_AVG_CTE}
        SELECT {expression} AS bucket,
        {_ANALYTICS_MEASURES}
        {_ANALYTICS_FROM}
        {where}
        GROUP BY {expression}
        ORDER BY {"bucket" if dimension in ORDERED_DIMENSIONS else "n DESC"}
    """
    if limit is not None:
        sql += " FETCH FIRST :row_limit ROWS ONLY"
        binds["row_limit"] = limit

    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(sql, **binds)
        cols = [d[0].lower() for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        for row in rows:
            for key in ("matched_cost", "matched_grams", "class_cost", "class_grams", "avg_confidence"):
                row[key] = float(row[key]) if row[key] is not None else 0.0
        return rows


def analytics_totals(
    days: int | None = 30,
    building_id: int | None = None,
    can_id: int | None = None,
    category: str | None = None,
    material: str | None = None,
    detected_object: str | None = None,
    supplier: str | None = None,
) -> dict:
    """The same measures with no grouping: the headline row."""
    where, binds = _analytics_filters(
        days, building_id, can_id, category, material, detected_object, supplier
    )
    sql = f"""
        {_LABEL_AVG_CTE}
        SELECT {_ANALYTICS_MEASURES}
        {_ANALYTICS_FROM}
        {where}
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(sql, **binds)
        cols = [d[0].lower() for d in cursor.description]
        row = dict(zip(cols, cursor.fetchone()))
        for key in ("matched_cost", "matched_grams", "class_cost", "class_grams", "avg_confidence"):
            row[key] = float(row[key]) if row[key] is not None else 0.0
        return row


def analytics_misrouted(
    days: int | None = 30,
    building_id: int | None = None,
    can_id: int | None = None,
    category: str | None = None,
    material: str | None = None,
    detected_object: str | None = None,
    supplier: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Items put in a bin the catalog says is the wrong one.

    This is the wrong-bin view, and it is only answerable because the
    catalog records which bin each product SHOULD go in. Both sides are stored
    facts -- the logged category and the catalog's intended stream -- so a row
    here is a real disagreement, not a model opinion.
    """
    where, binds = _analytics_filters(
        days, building_id, can_id, category, material, detected_object, supplier
    )
    extra = "p.disposal_category IS NOT NULL AND we.category IS NOT NULL AND p.disposal_category <> we.category"
    where = f"{where} AND {extra}" if where else f"WHERE {extra}"
    binds["row_limit"] = limit

    sql = f"""
        {_LABEL_AVG_CTE}
        SELECT COALESCE(p.product_name, we.detected_object) AS item,
               we.category AS logged_as,
               p.disposal_category AS should_be,
               COUNT(*) AS n,
               SUM(CASE WHEN p.unit_weight_grams IS NOT NULL THEN p.unit_weight_grams ELSE 0 END) AS grams
        {_ANALYTICS_FROM}
        {where}
        GROUP BY COALESCE(p.product_name, we.detected_object), we.category, p.disposal_category
        ORDER BY n DESC
        FETCH FIRST :row_limit ROWS ONLY
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(sql, **binds)
        return [
            {"item": r[0], "logged_as": r[1], "should_be": r[2], "count": r[3],
             "grams": float(r[4]) if r[4] is not None else 0.0}
            for r in cursor.fetchall()
        ]


def analytics_bin_composition(
    days: int | None = 30,
    building_id: int | None = None,
    can_id: int | None = None,
    category: str | None = None,
    material: str | None = None,
    detected_object: str | None = None,
    supplier: str | None = None,
    top_items_per_can: int = 5,
) -> list[dict]:
    """The top few items in each can: "what is usually in this bin".

    Ranked inside each can with ROW_NUMBER rather than filtered globally, so a
    quiet can still shows its own top items instead of being crowded out of a
    campus-wide top-N by the dining halls.
    """
    where, binds = _analytics_filters(
        days, building_id, can_id, category, material, detected_object, supplier
    )
    extra = "we.bin_id IS NOT NULL"
    where = f"{where} AND {extra}" if where else f"WHERE {extra}"
    binds["per_can"] = top_items_per_can

    sql = f"""
        {_LABEL_AVG_CTE}, per_can AS (
            SELECT c.can_id, c.can_code, b.name AS building_name,
                   COALESCE(p.product_name, we.detected_object, 'unidentified') AS item,
                   COALESCE(we.category, 'unknown') AS category,
                   COUNT(*) AS n,
                   SUM(COALESCE(p.unit_cost, la.avg_cost, 0)) AS est_cost
            {_ANALYTICS_FROM}
            {where}
            GROUP BY c.can_id, c.can_code, b.name,
                     COALESCE(p.product_name, we.detected_object, 'unidentified'),
                     COALESCE(we.category, 'unknown')
        )
        SELECT can_id, can_code, building_name, item, category, n, est_cost
        FROM (
            SELECT per_can.*,
                   ROW_NUMBER() OVER (PARTITION BY can_id ORDER BY n DESC, item) AS rn,
                   SUM(n) OVER (PARTITION BY can_id) AS can_total
            FROM per_can
        )
        WHERE rn <= :per_can
        ORDER BY can_total DESC, can_code, n DESC
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(sql, **binds)
        return [
            {"can_id": r[0], "can_code": r[1], "building_name": r[2], "item": r[3],
             "category": r[4], "count": r[5], "estimated_cost": float(r[6]) if r[6] else 0.0}
            for r in cursor.fetchall()
        ]


def analytics_review_rows(
    days: int | None = 30,
    building_id: int | None = None,
    can_id: int | None = None,
    category: str | None = None,
    material: str | None = None,
    detected_object: str | None = None,
    supplier: str | None = None,
) -> list[dict]:
    """The latest human verdict per reviewed event, with what the model said.

    Latest-per-event via ROW_NUMBER rather than a plain join: EVENT_REVIEWS is
    append-only so a contested call can carry two verdicts, and counting both
    would double-weight exactly the events people disagreed about.
    """
    where, binds = _analytics_filters(
        days, building_id, can_id, category, material, detected_object, supplier
    )
    sql = f"""
        {_LABEL_AVG_CTE}, latest AS (
            SELECT r.*, ROW_NUMBER() OVER (
                       PARTITION BY r.event_id ORDER BY r.reviewed_at DESC, r.review_id DESC
                   ) AS rn
            FROM event_reviews r
        )
        SELECT we.event_id, we.detected_object, we.category, we.confidence,
               latest.verdict, latest.corrected_category, latest.corrected_object
        {_ANALYTICS_FROM}
        JOIN latest ON latest.event_id = we.event_id AND latest.rn = 1
        {where}
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(sql, **binds)
        return [
            {"event_id": r[0], "detected_object": r[1], "category": r[2],
             "confidence": float(r[3]) if r[3] is not None else None,
             "verdict": r[4], "corrected_category": r[5], "corrected_object": r[6]}
            for r in cursor.fetchall()
        ]



def edible_food_waste(days: int = 30) -> list[dict]:
    """Discarded food the catalog marks as edible, by building and item.

    The 'edible food' tag is what separates a loss from a by-product. Peels,
    cores and spent grounds carry 'fruit residue' / 'spent grounds' instead
    and are priced at zero, because the product they came from was eaten --
    counting them here would turn a well-run dining hall into a problem on
    the dashboard.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT b.name AS building,
                   p.product_name AS item,
                   COUNT(*) AS n,
                   SUM(p.unit_cost) AS cost,
                   SUM(p.unit_weight_grams) AS grams
            FROM waste_events we
            JOIN products p ON p.product_id = we.product_id
            LEFT JOIN cans c ON c.can_id = we.bin_id
            LEFT JOIN buildings b ON b.building_id = c.building_id
            WHERE p.material_subtype = 'edible food'
              AND we.created_at >= SYSTIMESTAMP - :days
            GROUP BY b.name, p.product_name
            ORDER BY SUM(p.unit_cost) DESC
            """,
            days=days,
        )
        return [
            {
                "building": row[0],
                "item": row[1],
                "count": row[2],
                "cost": float(row[3]) if row[3] is not None else 0.0,
                "grams": float(row[4]) if row[4] is not None else 0.0,
            }
            for row in cursor.fetchall()
        ]


def analytics_filter_options(days: int | None = 30) -> dict:
    """The values actually present in the window, so the filter bar never
    offers a choice that yields an empty page."""
    with get_connection() as conn, conn.cursor() as cursor:
        def column(sql):
            cursor.execute(sql, days=days)
            return [r[0] for r in cursor.fetchall() if r[0] is not None]

        return {
            "categories": column(
                "SELECT DISTINCT category FROM waste_events "
                "WHERE created_at >= SYSTIMESTAMP - :days ORDER BY 1"
            ),
            "materials": column(
                "SELECT DISTINCT COALESCE(p.material, we.material) FROM waste_events we "
                "LEFT JOIN products p ON p.product_id = we.product_id "
                "WHERE we.created_at >= SYSTIMESTAMP - :days ORDER BY 1"
            ),
            "objects": column(
                "SELECT DISTINCT detected_object FROM waste_events "
                "WHERE created_at >= SYSTIMESTAMP - :days ORDER BY 1"
            ),
            "suppliers": column(
                "SELECT DISTINCT p.supplier FROM waste_events we "
                "JOIN products p ON p.product_id = we.product_id "
                "WHERE we.created_at >= SYSTIMESTAMP - :days ORDER BY 1"
            ),
        }



# ---------------------------------------------------------------------------
# Hazardous disposals (the hazards page)
# ---------------------------------------------------------------------------
# Every query here is scoped to HAZARD_FLAG = 1. HAZARD_STATUS predates this
# work and defaults to 'open' on all 1,090 rows including the ones that are
# not hazards, so it carries no information on its own and is never the
# filter.

_HAZARD_SELECT = """
SELECT we.event_id, we.detected_object, we.material, we.category,
       we.hazard_reason, we.hazard_class, we.hazard_severity, we.hazard_note,
       we.confidence, we.created_at, we.image_key,
       we.acknowledged_at, we.acknowledged_by,
       we.location, c.can_id, c.can_code, c.floor, c.placement_note,
       b.building_id, b.name AS building_name, b.campus_area
FROM waste_events we
LEFT JOIN cans c ON c.can_id = we.bin_id
LEFT JOIN buildings b ON b.building_id = c.building_id
WHERE we.hazard_flag = 1
"""


def _hazard_rows(cursor) -> list[dict]:
    cols = [d[0].lower() for d in cursor.description]
    rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    for row in rows:
        for key in ("created_at", "acknowledged_at"):
            if row.get(key):
                row[key] = row[key].strftime("%Y-%m-%d %H:%M:%S")
        if row.get("confidence") is not None:
            row["confidence"] = float(row["confidence"])
    return rows


def list_hazard_disposals(
    days: int = 30,
    severity: str | None = None,
    hazard_class: str | None = None,
    building_id: int | None = None,
    outstanding_only: bool = False,
    limit: int = 200,
) -> list[dict]:
    """Flagged disposals, newest first, with the can and building they were
    found in.

    `outstanding_only` means nobody has acknowledged it yet, which is the
    page's default view: an operator opening this wants the work, not the
    archive.
    """
    clauses = []
    binds: dict = {"days": days, "row_limit": limit}
    clauses.append("AND we.created_at >= SYSTIMESTAMP - :days")
    if severity:
        clauses.append("AND we.hazard_severity = :severity")
        binds["severity"] = severity
    if hazard_class:
        clauses.append("AND we.hazard_class = :hazard_class")
        binds["hazard_class"] = hazard_class
    if building_id is not None:
        clauses.append("AND c.building_id = :building_id")
        binds["building_id"] = building_id
    if outstanding_only:
        clauses.append("AND we.acknowledged_at IS NULL")

    sql = (
        _HAZARD_SELECT
        + "\n".join(clauses)
        + "\nORDER BY we.created_at DESC FETCH FIRST :row_limit ROWS ONLY"
    )
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(sql, **binds)
        return _hazard_rows(cursor)


def hazard_class_counts(days: int = 30) -> list[dict]:
    """Counts by class and severity, with how many are still outstanding."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COALESCE(hazard_class, 'unclassified') AS hazard_class,
                   COALESCE(hazard_severity, 'unclassified') AS severity,
                   COUNT(*) AS n,
                   SUM(CASE WHEN acknowledged_at IS NULL THEN 1 ELSE 0 END) AS outstanding
            FROM waste_events
            WHERE hazard_flag = 1 AND created_at >= SYSTIMESTAMP - :days
            GROUP BY COALESCE(hazard_class, 'unclassified'),
                     COALESCE(hazard_severity, 'unclassified')
            ORDER BY n DESC
            """,
            days=days,
        )
        return [
            {"hazard_class": r[0], "severity": r[1], "count": r[2], "outstanding": r[3]}
            for r in cursor.fetchall()
        ]


def hazard_location_counts(days: int = 30) -> list[dict]:
    """Where hazards are turning up, by building and class.

    This is the query the recurrence alert is built on: the same class in the
    same building repeatedly is a missing collection point, not a run of
    careless individuals.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COALESCE(b.name, 'unattributed') AS building_name,
                   b.building_id,
                   COALESCE(we.hazard_class, 'unclassified') AS hazard_class,
                   COALESCE(we.hazard_severity, 'unclassified') AS severity,
                   COUNT(*) AS n,
                   MAX(we.created_at) AS last_seen,
                   COUNT(DISTINCT c.can_id) AS cans
            FROM waste_events we
            LEFT JOIN cans c ON c.can_id = we.bin_id
            LEFT JOIN buildings b ON b.building_id = c.building_id
            WHERE we.hazard_flag = 1 AND we.created_at >= SYSTIMESTAMP - :days
            GROUP BY b.name, b.building_id, we.hazard_class, we.hazard_severity
            ORDER BY n DESC
            """,
            days=days,
        )
        return [
            {
                "building_name": r[0],
                "building_id": r[1],
                "hazard_class": r[2],
                "severity": r[3],
                "count": r[4],
                "last_seen": r[5].strftime("%Y-%m-%d %H:%M:%S") if r[5] else None,
                "cans": r[6],
            }
            for r in cursor.fetchall()
        ]


def hazard_trend(days: int = 30) -> list[dict]:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT TO_CHAR(created_at, 'YYYY-MM-DD') AS day,
                   COALESCE(hazard_severity, 'unclassified') AS severity,
                   COUNT(*) AS n
            FROM waste_events
            WHERE hazard_flag = 1 AND created_at >= SYSTIMESTAMP - :days
            GROUP BY TO_CHAR(created_at, 'YYYY-MM-DD'),
                     COALESCE(hazard_severity, 'unclassified')
            ORDER BY day
            """,
            days=days,
        )
        return [{"date": r[0], "severity": r[1], "count": r[2]} for r in cursor.fetchall()]


def acknowledge_hazard(event_id: int, acknowledged_by: str, note: str | None = None) -> bool:
    """Marks one hazard as dealt with. Returns False when it was already
    acknowledged, so the API can say so rather than silently overwriting
    whoever got there first."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE waste_events
               SET acknowledged_at = SYSTIMESTAMP,
                   acknowledged_by = :acknowledged_by,
                   hazard_note = :note,
                   hazard_status = 'acknowledged'
             WHERE event_id = :event_id
               AND hazard_flag = 1
               AND acknowledged_at IS NULL
            """,
            event_id=event_id,
            acknowledged_by=acknowledged_by,
            note=note,
        )
        changed = cursor.rowcount
        conn.commit()
        return changed > 0


def set_hazard_classification(rows: list[dict]) -> int:
    """Batch-writes {event_id, hazard_class, hazard_severity} back onto
    flagged events, so the classification is stored rather than recomputed on
    every page load and can be queried and grouped in SQL."""
    if not rows:
        return 0
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.executemany(
            """
            UPDATE waste_events
               SET hazard_class = :hazard_class, hazard_severity = :hazard_severity
             WHERE event_id = :event_id
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def list_unclassified_hazards() -> list[tuple]:
    """(event_id, detected_object, hazard_reason) for flagged events that have
    no class yet -- what the classifier backfill works through."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT event_id, detected_object, hazard_reason
            FROM waste_events
            WHERE hazard_flag = 1 AND hazard_class IS NULL
            ORDER BY event_id
            """
        )
        return cursor.fetchall()


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


def can_activity_cells(
    days: int = 14,
    building_id: int | None = None,
    model_id: int | None = None,
) -> list[dict]:
    """Disposal counts bucketed by can, ISO weekday, and hour of day.

    One row per (can, weekday, hour) that actually saw a disposal -- the result
    is sparse, not a dense 43 x 7 x 24 grid, because most buckets are empty and
    sending the zeros would be ~7k rows of nothing. fleet.py densifies the
    small summaries the UI needs and leaves the per-can cells sparse.

    day_of_week is 0 = Monday .. 6 = Sunday, computed as the day offset from
    the start of the ISO week rather than TO_CHAR(.., 'D'), whose numbering
    depends on the session's NLS_TERRITORY and would silently rotate the
    heatmap's rows on a differently configured client.

    Only active cans are counted, matching db.list_can_rows: a removed can is
    not on the map, so its history must not colour the campus heatmap either.
    Events with no BIN_ID (test-harness captures that name no physical unit)
    are excluded by the join.
    """
    clauses = []
    binds: dict = {"days": days}
    if building_id is not None:
        clauses.append("AND c.building_id = :building_id")
        binds["building_id"] = building_id
    if model_id is not None:
        clauses.append("AND c.model_id = :model_id")
        binds["model_id"] = model_id

    sql = f"""
        SELECT we.bin_id AS can_id,
               TRUNC(we.created_at) - TRUNC(we.created_at, 'IW') AS day_of_week,
               EXTRACT(HOUR FROM we.created_at) AS hour_of_day,
               COUNT(*) AS n
        FROM waste_events we
        JOIN cans c ON c.can_id = we.bin_id
        WHERE c.lifecycle_status = 'active'
          AND we.created_at >= SYSTIMESTAMP - :days
          {" ".join(clauses)}
        GROUP BY we.bin_id,
                 TRUNC(we.created_at) - TRUNC(we.created_at, 'IW'),
                 EXTRACT(HOUR FROM we.created_at)
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(sql, **binds)
        return [
            {
                "can_id": int(can_id),
                "day_of_week": int(day_of_week),
                "hour_of_day": int(hour_of_day),
                "count": int(n),
            }
            for can_id, day_of_week, hour_of_day, n in cursor.fetchall()
        ]



# ---------------------------------------------------------------------------
# Initiatives and projects (the workspace)
# ---------------------------------------------------------------------------
# An initiative stores a measurement recipe rather than a number: METRIC
# plus the SCOPE_* columns, which mirror the analytics filter set. Progress
# is recomputed by initiatives.py on every read, so a goal cannot drift from
# the data it is about.

_INITIATIVE_COLUMNS = (
    "name", "description", "owner", "metric", "direction",
    "scope_building_id", "scope_category", "scope_material", "scope_object",
    "scope_supplier", "baseline_value", "baseline_window_days", "target_value",
    "target_date", "status",
)

_INITIATIVE_SELECT = """
SELECT initiative_id, name, description, owner, metric, direction,
       scope_building_id, scope_category, scope_material, scope_object,
       scope_supplier, baseline_value, baseline_window_days, baseline_captured_at,
       target_value, target_date, status, created_at, updated_at
FROM initiatives
"""


def _initiative_rows(cursor) -> list[dict]:
    cols = [d[0].lower() for d in cursor.description]
    rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    for row in rows:
        for key in ("baseline_captured_at", "created_at", "updated_at"):
            if row.get(key):
                row[key] = row[key].strftime("%Y-%m-%d %H:%M:%S")
        if row.get("target_date"):
            row["target_date"] = row["target_date"].strftime("%Y-%m-%d")
        for key in ("baseline_value", "target_value"):
            if row.get(key) is not None:
                row[key] = float(row[key])
    return rows


def list_initiatives(status: str | None = None) -> list[dict]:
    where = "WHERE status = :status" if status else ""
    binds = {"status": status} if status else {}
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            f"{_INITIATIVE_SELECT} {where} ORDER BY "
            "CASE status WHEN 'active' THEN 0 WHEN 'achieved' THEN 1 ELSE 2 END, "
            "target_date NULLS LAST, initiative_id",
            **binds,
        )
        return _initiative_rows(cursor)


def get_initiative(initiative_id: int) -> dict | None:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            f"{_INITIATIVE_SELECT} WHERE initiative_id = :initiative_id",
            initiative_id=initiative_id,
        )
        rows = _initiative_rows(cursor)
        return rows[0] if rows else None


def insert_initiative(**columns) -> int:
    """Creates one initiative. BASELINE_CAPTURED_AT is set here rather than
    supplied, because the baseline is only meaningful alongside the moment
    it was taken."""
    unknown = set(columns) - set(_INITIATIVE_COLUMNS)
    if unknown:
        raise ValueError(f"Not initiative columns: {sorted(unknown)}")

    names = list(columns)
    placeholders = ", ".join(f":{name}" for name in names)
    with get_connection() as conn, conn.cursor() as cursor:
        initiative_id_var = cursor.var(int)
        cursor.execute(
            f"""
            INSERT INTO initiatives ({", ".join(names)}, baseline_captured_at)
            VALUES ({placeholders}, SYSTIMESTAMP)
            RETURNING initiative_id INTO :initiative_id
            """,
            initiative_id=initiative_id_var,
            **columns,
        )
        conn.commit()
        return initiative_id_var.getvalue()[0]


def update_initiative(initiative_id: int, **columns) -> bool:
    """Updates the given columns. BASELINE_VALUE is deliberately not
    updatable: a baseline that moves is not a baseline, and letting one
    slide is the easiest way to make a missed target look met."""
    unknown = set(columns) - (set(_INITIATIVE_COLUMNS) - {"baseline_value"})
    if unknown:
        raise ValueError(f"Not updatable initiative columns: {sorted(unknown)}")
    if not columns:
        return False

    assignments = ", ".join(f"{name} = :{name}" for name in columns)
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE initiatives SET {assignments}, updated_at = SYSTIMESTAMP
             WHERE initiative_id = :initiative_id
            """,
            initiative_id=initiative_id,
            **columns,
        )
        changed = cursor.rowcount
        conn.commit()
        return changed > 0



def backdate_initiative_baseline(initiative_id: int, days_ago: int) -> bool:
    """Moves an initiative's baseline capture time into the past.

    Only the demo seed uses this. A baseline is meaningful alongside the
    moment it was taken, and seeded goals are meant to read as having been
    set weeks ago rather than this morning -- but the timestamp has to say
    so, or the page claims a baseline was measured today and then shows
    progress away from it, which is incoherent.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE initiatives
               SET baseline_captured_at = SYSTIMESTAMP - :days_ago,
                   created_at = SYSTIMESTAMP - :days_ago
             WHERE initiative_id = :initiative_id
            """,
            initiative_id=initiative_id,
            days_ago=days_ago,
        )
        changed = cursor.rowcount
        conn.commit()
        return changed > 0


def delete_initiative(initiative_id: int) -> bool:
    """Removes an initiative and detaches its projects.

    The projects survive, orphaned rather than deleted: the work may have
    happened and may belong to another goal, and quietly destroying a record
    of what somebody did because a target was retired is not the database's
    decision to make.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "UPDATE projects SET initiative_id = NULL WHERE initiative_id = :initiative_id",
            initiative_id=initiative_id,
        )
        cursor.execute(
            "DELETE FROM initiatives WHERE initiative_id = :initiative_id",
            initiative_id=initiative_id,
        )
        changed = cursor.rowcount
        conn.commit()
        return changed > 0


_PROJECT_COLUMNS = (
    "initiative_id", "name", "description", "owner", "status",
    "expected_impact", "expected_impact_note", "source_recommendation_key",
    "due_date", "started_at", "completed_at",
)

_PROJECT_SELECT = """
SELECT project_id, initiative_id, name, description, owner, status,
       expected_impact, expected_impact_note, source_recommendation_key,
       due_date, started_at, completed_at, created_at, updated_at
FROM projects
"""


def _project_rows(cursor) -> list[dict]:
    cols = [d[0].lower() for d in cursor.description]
    rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
    for row in rows:
        for key in ("started_at", "completed_at", "created_at", "updated_at"):
            if row.get(key):
                row[key] = row[key].strftime("%Y-%m-%d %H:%M:%S")
        if row.get("due_date"):
            row["due_date"] = row["due_date"].strftime("%Y-%m-%d")
        if row.get("expected_impact") is not None:
            row["expected_impact"] = float(row["expected_impact"])
    return rows


def list_projects(initiative_id: int | None = None, status: str | None = None) -> list[dict]:
    clauses = []
    binds: dict = {}
    if initiative_id is not None:
        clauses.append("initiative_id = :initiative_id")
        binds["initiative_id"] = initiative_id
    if status:
        clauses.append("status = :status")
        binds["status"] = status
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            f"{_PROJECT_SELECT} {where} ORDER BY "
            "CASE status WHEN 'in_progress' THEN 0 WHEN 'blocked' THEN 1 "
            "WHEN 'proposed' THEN 2 WHEN 'done' THEN 3 ELSE 4 END, "
            "due_date NULLS LAST, project_id",
            **binds,
        )
        return _project_rows(cursor)


def get_project(project_id: int) -> dict | None:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            f"{_PROJECT_SELECT} WHERE project_id = :project_id", project_id=project_id
        )
        rows = _project_rows(cursor)
        return rows[0] if rows else None


def insert_project(**columns) -> int:
    unknown = set(columns) - set(_PROJECT_COLUMNS)
    if unknown:
        raise ValueError(f"Not project columns: {sorted(unknown)}")
    names = list(columns)
    placeholders = ", ".join(f":{name}" for name in names)
    with get_connection() as conn, conn.cursor() as cursor:
        project_id_var = cursor.var(int)
        cursor.execute(
            f"""
            INSERT INTO projects ({", ".join(names)})
            VALUES ({placeholders})
            RETURNING project_id INTO :project_id
            """,
            project_id=project_id_var,
            **columns,
        )
        conn.commit()
        return project_id_var.getvalue()[0]


def update_project(project_id: int, **columns) -> bool:
    unknown = set(columns) - set(_PROJECT_COLUMNS)
    if unknown:
        raise ValueError(f"Not project columns: {sorted(unknown)}")
    if not columns:
        return False
    assignments = ", ".join(f"{name} = :{name}" for name in columns)
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            f"""
            UPDATE projects SET {assignments}, updated_at = SYSTIMESTAMP
             WHERE project_id = :project_id
            """,
            project_id=project_id,
            **columns,
        )
        changed = cursor.rowcount
        conn.commit()
        return changed > 0


def delete_project(project_id: int) -> bool:
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute("DELETE FROM projects WHERE project_id = :project_id",
                       project_id=project_id)
        changed = cursor.rowcount
        conn.commit()
        return changed > 0


def project_keys_in_use() -> set[str]:
    """Recommendation keys already turned into a project, so the
    recommendations page can show which of its cards are being acted on
    rather than offering the same work twice."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT DISTINCT source_recommendation_key FROM projects "
            "WHERE source_recommendation_key IS NOT NULL AND status <> 'cancelled'"
        )
        return {row[0] for row in cursor.fetchall()}


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
