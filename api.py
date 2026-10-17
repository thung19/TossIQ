"""FastAPI service for TossIQ.

Two sorting entry points, matching the PRD's two-layer architecture:

- POST /sort     -- fast path (Layer 1). Runs the lightweight YOLOE detector,
                     returns a sort decision immediately, then enriches and
                     persists the event with the slower Qwen analysis (Layer 2)
                     in a background task so the caller never waits on it.
- POST /classify -- direct advanced-analysis path (Layer 2 only). Used for
                     testing; also persists its result.

Everything else (catalog, dashboard stats, recommendations) is plain CRUD/
aggregation over the OCI-backed tables in db.py (Layer 3).

GET / serves the dashboard (static/index.html) -- a live view over the
same stats/recommendations/products endpoints below.

The models are loaded once at startup (see `lifespan`) and reused across
requests via `app.state`.

Run locally:
    uvicorn api:app --reload

    Or, if port 8000 may already be taken by another local process and you
    don't want to hunt for a free port yourself:
    python run_api.py
"""

import io
import logging
import uuid

from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

import db
import insights
import oci_storage
from fast_sort import detect as fast_detect
from fast_sort import load_fast_model
from identify import load_model
from main import run as run_advanced
from sorting import load_rules

logger = logging.getLogger("tossiq")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}

# Heuristic confidence (0-100) for the advanced path -- Qwen does not report
# a calibrated numeric confidence, so this is derived from how much of the
# identification parsed cleanly. Stored in WASTE_EVENTS.confidence, which the
# dashboard should present as a model-derived estimate, not a measured fact
# (PRD design principle 3).
CONFIDENCE_PARSE_ERROR = 20
CONFIDENCE_PARTIAL = 55
CONFIDENCE_FULL = 90


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.model_handle = load_model()
    app.state.rules = load_rules()
    app.state.fast_model = load_fast_model()
    yield


app = FastAPI(title="TossIQ Classification API", lifespan=lifespan)


class ClassificationResponse(BaseModel):
    object: str | None = None
    material: str | None = None
    material_subtype: str | None = None
    food_contaminated: bool | None = None
    category: str
    reason: str
    matched_rule: str | None = None
    parse_error: str | None = None
    event_id: int | None = None
    matched_product: str | None = None


class SortResponse(BaseModel):
    label: str | None = None
    category: str
    confidence: float | None = None
    needs_review: bool
    reason: str


class ProductIn(BaseModel):
    product_name: str
    supplier: str | None = None
    sku: str | None = None
    material: str | None = None
    unit_cost: float | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


def _decode_upload(contents: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(contents))
        image.load()  # force full decode now so truncated/corrupt files fail here, not mid-inference
        return image.convert("RGB")
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="File is not a valid image")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read uploaded image")


async def _read_and_validate_upload(file: UploadFile) -> bytes:
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content type {file.content_type!r}; expected one of {sorted(ALLOWED_CONTENT_TYPES)}",
        )
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="Image exceeds 10MB upload limit")
    return contents


def _confidence_for(identification: dict) -> int:
    if identification.get("parse_error"):
        return CONFIDENCE_PARSE_ERROR
    if identification.get("object") and identification.get("material"):
        return CONFIDENCE_FULL
    return CONFIDENCE_PARTIAL


def _upload_event_image(image: Image.Image) -> str | None:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    key = f"events/{uuid.uuid4().hex}.jpg"
    return oci_storage.upload_image(buffer.getvalue(), key)


def _persist_advanced_result(
    image: Image.Image, identification: dict, sorting_result: dict, location: str | None
) -> tuple[int, dict | None]:
    matched_product = db.match_product(identification.get("object"))
    image_key = _upload_event_image(image)
    event_id = db.insert_waste_event(
        detected_object=identification.get("object"),
        material=identification.get("material"),
        category=sorting_result["category"],
        location=location,
        confidence=_confidence_for(identification),
        image_key=image_key,
        product_id=matched_product["product_id"] if matched_product else None,
    )
    return event_id, matched_product


def _run_advanced_and_persist(image: Image.Image, handle, rules, location: str | None) -> None:
    """Background-task body: run the slow Qwen analysis and persist the result.

    Never raises into the caller -- this runs detached from the request that
    already returned a fast /sort response, so failures are logged, not
    surfaced, per PRD section 2A ("continue ... even when cloud/advanced
    services are unavailable").
    """
    try:
        result = run_advanced(image, handle=handle, rules=rules)
        _persist_advanced_result(image, result["identification"], result["sorting"], location)
    except Exception:
        logger.exception("Background advanced analysis failed")


@app.post("/classify", response_model=ClassificationResponse)
async def classify(file: UploadFile = File(...), location: str | None = Form(None)):
    contents = await _read_and_validate_upload(file)
    image = _decode_upload(contents)

    try:
        result = run_advanced(image, handle=app.state.model_handle, rules=app.state.rules)
    except Exception:
        logger.exception("Inference failed")
        raise HTTPException(status_code=500, detail="Inference failed")

    identification = result["identification"]
    sorting_result = result["sorting"]
    event_id, matched_product = _persist_advanced_result(image, identification, sorting_result, location)

    return ClassificationResponse(
        object=identification.get("object"),
        material=identification.get("material"),
        material_subtype=identification.get("material_subtype"),
        food_contaminated=identification.get("food_contaminated"),
        category=sorting_result["category"],
        reason=sorting_result["reason"],
        matched_rule=sorting_result["matched_rule"],
        parse_error=identification.get("parse_error"),
        event_id=event_id,
        matched_product=matched_product["product_name"] if matched_product else None,
    )


@app.post("/sort", response_model=SortResponse)
async def sort(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    location: str | None = Form(None),
):
    """Fast path: immediate sort decision from the lightweight local model.

    The physical sorting mechanism (not yet integrated in hardware) would be
    triggered here, directly from this fast result -- per PRD section 2A,
    it must not wait on the code below this line.
    """
    contents = await _read_and_validate_upload(file)
    image = _decode_upload(contents)

    fast_result = fast_detect(app.state.fast_model, image)

    # TODO(hardware): trigger the physical sorting mechanism here with
    # fast_result["category"], once it's wired to the Raspberry Pi.
    if fast_result["needs_review"]:
        logger.info("Fast sort flagged for manual review: %s", fast_result["reason"])

    background_tasks.add_task(
        _run_advanced_and_persist,
        image,
        app.state.model_handle,
        app.state.rules,
        location,
    )

    return SortResponse(**fast_result)


@app.post("/enrich")
async def enrich(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    fast_category: str | None = Form(None),
    fast_label: str | None = Form(None),
    fast_confidence: float | None = Form(None),
    location: str | None = Form(None),
):
    """Advanced-analysis path for a frame already fast-sorted on the edge device.

    The caller (edge/pi_sort_client.py) already ran the fast model locally
    and triggered the physical sort there -- this endpoint only runs the
    slow Qwen analysis and persists the result, same as /sort's background
    task. The fast category/label/confidence are informational only;
    WASTE_EVENTS.CATEGORY still records the advanced-analysis category,
    same as today.
    """
    contents = await _read_and_validate_upload(file)
    image = _decode_upload(contents)

    logger.info(
        "Received already-sorted item: fast_category=%s fast_label=%s fast_confidence=%s",
        fast_category,
        fast_label,
        fast_confidence,
    )

    background_tasks.add_task(
        _run_advanced_and_persist,
        image,
        app.state.model_handle,
        app.state.rules,
        location,
    )

    return {"status": "accepted"}


# ---------------------------------------------------------------------------
# Catalog (Experience 3)
# ---------------------------------------------------------------------------

@app.get("/products")
def get_products():
    return db.list_products()


@app.post("/products")
def create_product(product: ProductIn):
    product_id = db.add_product(
        product_name=product.product_name,
        supplier=product.supplier,
        sku=product.sku,
        material=product.material,
        unit_cost=product.unit_cost,
    )
    return {"product_id": product_id}


# ---------------------------------------------------------------------------
# Dashboard (Experience 4)
# ---------------------------------------------------------------------------

@app.get("/stats/overview")
def get_stats_overview(days: int = 30):
    return db.stats_overview(days=days)


@app.get("/stats/items")
def get_stats_items(days: int = 30):
    return db.stats_items(days=days)


@app.get("/stats/locations")
def get_stats_locations(days: int = 30):
    return db.stats_locations(days=days)


@app.get("/events/recent")
def get_events_recent(limit: int = 20):
    events = db.list_recent_events(limit=limit)
    for event in events:
        image_key = event.pop("image_key", None)
        event["image_url"] = oci_storage.get_presigned_url(image_key) if image_key else None
    return events


# ---------------------------------------------------------------------------
# Insights / recommendations (Experience 5)
# ---------------------------------------------------------------------------

@app.get("/recommendations")
def get_recommendations(limit: int = 20):
    return db.list_recommendations(limit=limit)


@app.post("/recommendations/generate")
def generate_recommendations(days: int = 30):
    new_texts = insights.generate_recommendations(days=days)
    return {"new_recommendations": new_texts}


# ---------------------------------------------------------------------------
# Dashboard UI -- mounted last so it never shadows the API routes above
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory="static", html=True), name="dashboard")
