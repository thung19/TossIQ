"""OCI Autonomous DB access layer for TossIQ.

All disposal-event persistence, catalog (PRODUCTS) lookups, and
recommendation storage go through here. Kept deliberately thin: plain
SQL over python-oracledb, no ORM, since the schema is small and already
fixed in OCI (WASTE_EVENTS / PRODUCTS / RECOMMENDATIONS).

Connections are opened per call rather than pooled -- simplest thing that
works for a hackathon demo's request volume. Swap for a oracledb.create_pool()
if this becomes a bottleneck.
"""

import math
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
    image_embedding=None,
) -> int:
    """created_at, when given, is the actual capture/disposal time (e.g. from an
    edge device queued during a network outage) rather than persist time; it is
    passed straight through as a bind value, so SYSTIMESTAMP is only used when
    the caller has no capture-time timestamp to report.

    image_embedding is the item photo's Cohere Embed v4 embedding, stored so the
    event joins the organization's searchable visual history (find_similar_events,
    cluster_unknown_events). It is optional: the embedding call is best-effort and
    returns None on failure (image_embed.embed_image), and a missing embedding
    must never cost the disposal event itself, so None stores NULL and the row
    persists unchanged."""
    created_at_sql = ":created_at" if created_at is not None else "SYSTIMESTAMP"
    embedding_sql = (
        "TO_VECTOR(:image_embedding_str, 1536, FLOAT32)" if image_embedding is not None else "NULL"
    )
    with get_connection() as conn, conn.cursor() as cursor:
        event_id_var = cursor.var(int)
        cursor.execute(
            f"""
            INSERT INTO waste_events
                (product_id, detected_object, material, category, location, confidence, image_key, created_at,
                 hazard_flag, hazard_reason, visible_text, reusable_condition, image_embedding)
            VALUES
                (:product_id, :detected_object, :material, :category, :location, :confidence, :image_key, {created_at_sql},
                 :hazard_flag, :hazard_reason, :visible_text, :reusable_condition, {embedding_sql})
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
            **(
                {"image_embedding_str": _vector_literal(image_embedding)}
                if image_embedding is not None
                else {}
            ),
        )
        conn.commit()
        return event_id_var.getvalue()[0]


# ---------------------------------------------------------------------------
# Visual memory (WASTE_EVENTS.IMAGE_EMBEDDING)
# ---------------------------------------------------------------------------
#
# Every advanced-analysis event stores the item photo's Cohere Embed v4
# embedding alongside the row (see insert_waste_event). That turns the same
# Oracle AI Database vector search the catalog already uses for a single
# lookup (match_product_by_image) into a search over the organization's own
# disposal history: the visually closest past disposals of any event
# (find_similar_events), and groups of repeatedly-discarded items that
# matched no catalog product at all (cluster_unknown_events).

# Cosine-distance ceiling for calling two unmatched item photos "the same
# item". Like match_product_by_image's max_distance this is a heuristic, not
# an empirically tuned value -- it has not been exercised against a real body
# of disposal photos, so expect to tune it once there is one.
UNKNOWN_CLUSTER_MAX_DISTANCE = 0.25

# Most recent unmatched events cluster_unknown_events will compare. The
# grouping is pairwise, so an unbounded window would let one request grow to
# tens of seconds of pure-Python vector arithmetic; the newest few hundred
# unmatched events are what a blind-spot report is about anyway.
UNKNOWN_CLUSTER_MAX_CANDIDATES = 500

# Groups smaller than this are dropped from cluster_unknown_events' output:
# the point of the view is what an organization throws away *repeatedly* but
# has never catalogued, and a single sighting is not yet that.
UNKNOWN_CLUSTER_MIN_SIZE = 2


def find_similar_events(event_id: int, limit: int = 6) -> list[dict]:
    """The visually closest past disposals to `event_id`, nearest first.

    Cosine distance over the stored image embeddings via Oracle's native
    VECTOR_DISTANCE, same operator and metric match_product_by_image uses for
    catalog lookups -- the subject event's embedding is read from its own row
    by self-join rather than passed in, so no re-embedding is needed. The
    `distance` is returned with each row because the UI shows it.

    Unlike match_product_by_image there is no distance ceiling here: this is a
    nearest-neighbour browse, so the caller sees the closest matches and how
    close they actually are rather than an empty result. Events with no stored
    embedding (captured before this column existed, or whose embedding call
    failed) cannot participate and are excluded on both sides; if the subject
    event is one of them the result is empty.

    Raises LookupError when `event_id` does not exist, which the API layer
    turns into a 404.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM waste_events WHERE event_id = :event_id",
            event_id=event_id,
        )
        if cursor.fetchone() is None:
            raise LookupError(f"No event with event_id {event_id}")

        cursor.execute(
            """
            SELECT other.event_id, other.detected_object, other.material, other.category,
                   other.location, other.image_key, other.created_at,
                   VECTOR_DISTANCE(other.image_embedding, subject.image_embedding, COSINE) AS distance
            FROM waste_events other, waste_events subject
            WHERE subject.event_id = :event_id
              AND subject.image_embedding IS NOT NULL
              AND other.image_embedding IS NOT NULL
              AND other.event_id <> :event_id
            ORDER BY distance
            FETCH FIRST :limit ROWS ONLY
            """,
            event_id=event_id,
            limit=limit,
        )
        cols = [d[0].lower() for d in cursor.description]
        rows = [dict(zip(cols, row)) for row in cursor.fetchall()]
        for row in rows:
            row["distance"] = float(row["distance"])
            if row["created_at"]:
                row["created_at"] = row["created_at"].strftime("%Y-%m-%d %H:%M:%S")
        return rows


def _vector_norm(vector) -> float:
    return math.sqrt(sum(a * a for a in vector))


def _cosine_distance(left, right, left_norm=None, right_norm=None) -> float:
    """Cosine distance between two embeddings, defined exactly as Oracle's
    VECTOR_DISTANCE(..., COSINE): 1 - cosine similarity, so 0 is identical.

    Computed in Python rather than SQL because the greedy grouping below
    needs every pairwise distance within one candidate set, and plain
    arithmetic over 1536 floats avoids both a query per pair and a numeric
    dependency. A zero-magnitude vector has no direction to compare, so it is
    reported as maximally distant (1.0) rather than dividing by zero.

    Either norm may be supplied when the caller already has it, so a vector
    compared against many others is not re-normed once per pair.
    """
    dot = sum(a * b for a, b in zip(left, right))
    if left_norm is None:
        left_norm = _vector_norm(left)
    if right_norm is None:
        right_norm = _vector_norm(right)
    if left_norm == 0.0 or right_norm == 0.0:
        return 1.0
    return 1.0 - dot / (left_norm * right_norm)


def _group_by_similarity(events: list[dict], max_distance: float) -> list[list[dict]]:
    """Greedy single-pass visual grouping of `events` (each a dict carrying an
    `embedding`), largest group first.

    Walks the list in order; the first unassigned event seeds a group and
    pulls in every later unassigned event within `max_distance` of that seed.
    Every event therefore lands in exactly one group, and the seed -- the
    event the others were actually measured against -- is each group's first
    member and its representative.

    Deliberately not k-means/DBSCAN/hierarchical: there is no cluster count to
    choose, the result is stable and explainable ("these are all within
    `max_distance` of that photo"), and it needs no clustering dependency.
    The cost is order-sensitivity at the margins -- an event near two seeds
    joins whichever seeded first -- which is acceptable for surfacing
    repeatedly-discarded items.
    """
    # Each candidate's magnitude is a property of the vector alone, so it is
    # computed once here rather than once per pair it takes part in.
    norms = [_vector_norm(event["embedding"]) for event in events]
    groups: list[list[dict]] = []
    assigned: set[int] = set()
    for index, seed in enumerate(events):
        if index in assigned:
            continue
        assigned.add(index)
        members = [seed]
        for other_index in range(index + 1, len(events)):
            if other_index in assigned:
                continue
            distance = _cosine_distance(
                seed["embedding"],
                events[other_index]["embedding"],
                norms[index],
                norms[other_index],
            )
            if distance <= max_distance:
                assigned.add(other_index)
                members.append(events[other_index])
        groups.append(members)
    # Stable sort, so groups of equal size keep the order their seeds appeared in.
    groups.sort(key=len, reverse=True)
    return groups


def cluster_unknown_events(
    days: int = 30,
    max_distance: float = UNKNOWN_CLUSTER_MAX_DISTANCE,
    min_size: int = UNKNOWN_CLUSTER_MIN_SIZE,
    max_candidates: int = UNKNOWN_CLUSTER_MAX_CANDIDATES,
) -> dict:
    """Unknown-item discovery: events in the window that matched no catalog
    product (PRODUCT_ID IS NULL) but do carry an image embedding, grouped by
    visual similarity, most-repeated group first.

    This is the blind-spot report -- what the organization keeps throwing away
    that nobody has catalogued -- so the caller can offer to teach it as a
    catalog product. `unmatched_events` reports how many events were
    considered, so a caller showing no groups can say whether that is because
    there were no unmatched events or because none repeated. At most
    `max_candidates` events are considered, the most recent first, because the
    grouping compares every candidate against every other.

    Each group reports `representative_event_id` (the member every other
    member's distance was measured against) rather than a nested copy of that
    member, so a member appears exactly once in the payload.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT event_id, detected_object, material, category, location, image_key,
                   created_at, image_embedding
            FROM waste_events
            WHERE product_id IS NULL
              AND image_embedding IS NOT NULL
              AND created_at >= SYSTIMESTAMP - :days
            ORDER BY created_at DESC
            FETCH FIRST :max_candidates ROWS ONLY
            """,
            days=days,
            max_candidates=max_candidates,
        )
        candidates = [
            {
                "event_id": row[0],
                "detected_object": row[1],
                "material": row[2],
                "category": row[3],
                "location": row[4],
                "image_key": row[5],
                "created_at": row[6],
                "embedding": row[7],
            }
            for row in cursor.fetchall()
        ]

    clusters = []
    for members in _group_by_similarity(candidates, max_distance):
        if len(members) < min_size:
            continue
        timestamps = [m["created_at"] for m in members if m["created_at"]]
        clusters.append(
            {
                "size": len(members),
                "representative_event_id": members[0]["event_id"],
                "first_seen": min(timestamps).strftime("%Y-%m-%d %H:%M:%S") if timestamps else None,
                "last_seen": max(timestamps).strftime("%Y-%m-%d %H:%M:%S") if timestamps else None,
                "members": [
                    {
                        "event_id": m["event_id"],
                        "detected_object": m["detected_object"],
                        "material": m["material"],
                        "category": m["category"],
                        "location": m["location"],
                        "image_key": m["image_key"],
                        "created_at": (
                            m["created_at"].strftime("%Y-%m-%d %H:%M:%S") if m["created_at"] else None
                        ),
                    }
                    for m in members
                ],
            }
        )

    return {
        "window_days": days,
        "max_distance": max_distance,
        "unmatched_events": len(candidates),
        "clusters": clusters,
    }


def list_events_missing_embedding(limit: int | None = None) -> list[dict]:
    """Events that have a stored image but no image embedding yet -- the work
    queue for backfill_event_embeddings.py.

    Rows are returned oldest-first so a run interrupted partway through makes
    predictable progress, and because the update it performs removes a row
    from this result, the script is re-runnable without repeating work.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        row_limit = "FETCH FIRST :limit ROWS ONLY" if limit is not None else ""
        cursor.execute(
            f"""
            SELECT event_id, image_key
            FROM waste_events
            WHERE image_key IS NOT NULL AND image_embedding IS NULL
            ORDER BY created_at
            {row_limit}
            """,
            **({"limit": limit} if limit is not None else {}),
        )
        return [{"event_id": row[0], "image_key": row[1]} for row in cursor.fetchall()]


def set_event_embedding(event_id: int, embedding: list[float]) -> None:
    """Stores an image embedding on an existing event, using the same
    TO_VECTOR() binding insert_waste_event and set_product_reference_embedding
    use. Raises LookupError when `event_id` does not exist."""
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE waste_events
            SET image_embedding = TO_VECTOR(:embedding_str, 1536, FLOAT32)
            WHERE event_id = :event_id
            """,
            embedding_str=_vector_literal(embedding),
            event_id=event_id,
        )
        if cursor.rowcount == 0:
            raise LookupError(f"No event with event_id {event_id}")
        conn.commit()


def get_event_image_key(event_id: int) -> str | None:
    """The Object Storage key of an event's stored photo, or None when the
    event has no image (the upload was skipped or failed).

    Lets a caller reuse an already-stored event photo server-side -- the
    waste-audit "teach this item" action attaching a group's representative
    photo as a product's reference image. Raises LookupError when `event_id`
    does not exist.
    """
    with get_connection() as conn, conn.cursor() as cursor:
        cursor.execute(
            "SELECT image_key FROM waste_events WHERE event_id = :event_id",
            event_id=event_id,
        )
        row = cursor.fetchone()
        if row is None:
            raise LookupError(f"No event with event_id {event_id}")
        return row[0]


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
