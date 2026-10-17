"""FastAPI service wrapping the existing Qwen identify -> rules-engine sort
pipeline (identify.py / sorting.py / main.run()) behind an HTTP endpoint.

The model is loaded once at startup (see `lifespan`) and reused across
requests via `app.state`. Device selection (CUDA/MPS/CPU) happens inside
identify.load_model(), so this file needs no device-specific code to run
unchanged locally (MPS) or on an OCI GPU shape (CUDA).

Run locally:
    uvicorn api:app --reload
"""

import io
import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel

from identify import load_model
from main import run
from sorting import load_rules

logger = logging.getLogger("tossiq")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Loaded once per process, not per-request -- this is the expensive step.
    app.state.model_handle = load_model()
    app.state.rules = load_rules()
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


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/classify", response_model=ClassificationResponse)
async def classify(file: UploadFile = File(...)):
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

    try:
        image = Image.open(io.BytesIO(contents))
        image.load()  # force full decode now so truncated/corrupt files fail here, not mid-inference
        image = image.convert("RGB")
    except UnidentifiedImageError:
        raise HTTPException(status_code=400, detail="File is not a valid image")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read uploaded image")

    try:
        result = run(image, handle=app.state.model_handle, rules=app.state.rules)
    except Exception:
        logger.exception("Inference failed")
        raise HTTPException(status_code=500, detail="Inference failed")

    identification = result["identification"]
    sorting = result["sorting"]

    return ClassificationResponse(
        object=identification.get("object"),
        material=identification.get("material"),
        material_subtype=identification.get("material_subtype"),
        food_contaminated=identification.get("food_contaminated"),
        category=sorting["category"],
        reason=sorting["reason"],
        matched_rule=sorting["matched_rule"],
        parse_error=identification.get("parse_error"),
    )
