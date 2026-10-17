"""Fast, lightweight local object detection + rough sort decision.

This is Layer 1 from the PRD: a cheap model that gives an immediate sort
decision so physical sorting never waits on the slower Qwen vision-language
model in identify.py. It intentionally does NOT attempt specific product
identification -- that nuance is Layer 2's job (identify.py, run async by
api.py's /sort endpoint).

Uses YOLOE (open-vocabulary detector) with a fixed label set rather than
training a custom model, per PRD section 9 ("Do not ... train large custom
models unless needed").
"""

from pathlib import Path

from ultralytics import YOLOE

MODEL_PATH = Path(__file__).with_name("yoloe-11s-seg.pt")

# Open-vocabulary labels the fast model looks for. Deliberately coarse --
# precise identification is Layer 2's job.
CLASSES = [
    "bottle",
    "can",
    "cup",
    "paper",
    "cardboard box",
    "banana peel",
    "apple core",
    "food scraps",
    "plastic bag",
    "food container",
    "food wrapper",
    "newspaper",
    "plastic container",
    "battery",
]

# Coarse label -> rough category, so the bin can move *something* before
# the advanced model's finer-grained rules.json classification lands.
# Mirrors sorting.py's CATEGORIES; "unknown" when a label is ambiguous
# (e.g. "cup" could be paper or plastic) rather than guessing wrong.
ROUGH_CATEGORY = {
    "bottle": "recycling",
    "can": "recycling",
    "cardboard box": "recycling",
    "newspaper": "recycling",
    "paper": "recycling",
    "plastic container": "recycling",
    "banana peel": "compost",
    "apple core": "compost",
    "food scraps": "compost",
    "plastic bag": "landfill",
    "food wrapper": "landfill",
    "food container": "unknown",  # could be clean (recycling) or contaminated (landfill)
    "cup": "unknown",
    "battery": "hazard",  # PRD section 2F: never auto-route on uncertain AI alone
}

CONFIDENCE_THRESHOLD = 0.25


def load_fast_model() -> YOLOE:
    model = YOLOE(str(MODEL_PATH))
    model.set_classes(CLASSES, model.get_text_pe(CLASSES))
    return model


def detect(model: YOLOE, image) -> dict:
    """Runs the fast detector on one frame/array/path.

    Returns the single highest-confidence detection as a sort decision, or
    an "unknown" / needs-review result if nothing clears the confidence
    threshold -- per PRD section 2A, uncertain classifications must not be
    confidently routed to the wrong bin.
    """
    results = model.predict(image, conf=CONFIDENCE_THRESHOLD, verbose=False)
    boxes = results[0].boxes
    if boxes is None or len(boxes) == 0:
        return {
            "label": None,
            "category": "unknown",
            "confidence": None,
            "needs_review": True,
            "reason": "No object detected above confidence threshold.",
        }

    best_idx = int(boxes.conf.argmax())
    label = results[0].names[int(boxes.cls[best_idx])]
    confidence = float(boxes.conf[best_idx])
    category = ROUGH_CATEGORY.get(label, "unknown")

    hazard = category == "hazard"
    return {
        "label": label,
        "category": "unknown" if hazard else category,
        "confidence": confidence,
        "needs_review": hazard or category == "unknown",
        "reason": (
            f"Possible hazardous item ({label}) -- flagged for manual review, not auto-routed."
            if hazard
            else f"Fast model matched {label!r} -> {category}."
        ),
    }


def _smoke_test() -> None:
    """Loads the model and runs one prediction to verify set_classes works end to end."""
    model = load_fast_model()
    result = detect(model, Path(__file__).with_name("images") / "test.jpg")
    print(result)


if __name__ == "__main__":
    _smoke_test()
