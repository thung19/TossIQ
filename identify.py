"""Qwen3-VL based waste-item identification.

Loads the model once via `load_model()`, then runs identification per image
with `identify_image()`. The model is asked to describe what it visually
sees (object / material / subtype / contamination) and is explicitly told
NOT to decide a disposal category -- that decision belongs to sorting.py's
rules engine, which can be tuned without touching the model or prompt.
"""

import json
import re
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoProcessor, Qwen3VLForConditionalGeneration

MODEL_ID = "Qwen/Qwen3-VL-2B-Instruct"

PROMPT = """
Identify the single main waste item in this image.

Return ONLY valid JSON with these fields:
{
  "object": "short name of the object, e.g. 'plastic water bottle'",
  "material": "one of: plastic, metal, glass, paper, cardboard, organic, other -- or null if you cannot tell",
  "material_subtype": "a more specific material if visually identifiable, e.g. 'PET', 'HDPE', 'aluminum', 'steel', 'corrugated cardboard' -- or null if you cannot tell",
  "food_contaminated": true if the item has visible food or liquid residue on it, false if it looks clean, or null if you cannot tell
}

Only describe what is visually identifiable in the image. Do not guess a
disposal category -- just describe the object. Use null for any field you
are not confident about.
Return ONLY the JSON object, with no extra text, explanation, or markdown fences.
"""

# Fields the model is asked for, and their "unset" default.
IDENTIFICATION_FIELDS = ("object", "material", "material_subtype", "food_contaminated")

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
_NULLISH_STRINGS = {"", "null", "none", "n/a", "unknown"}


class ModelHandle:
    """Bundles the loaded model, processor, and target device."""

    def __init__(self, model, processor, device):
        self.model = model
        self.processor = processor
        self.device = device


def select_device() -> str:
    """Picks the best available accelerator: CUDA (OCI GPU shapes) > MPS
    (Apple Silicon, local dev) > CPU. Keeps load_model() portable across
    both environments without any code changes."""
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model() -> ModelHandle:
    device = select_device()
    print(f"Using device: {device}")

    print("Loading Qwen...")
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        MODEL_ID,
        dtype=torch.float16 if device in ("cuda", "mps") else torch.float32,
        attn_implementation="sdpa",
    ).to(device)

    processor = AutoProcessor.from_pretrained(MODEL_ID)
    return ModelHandle(model, processor, device)


def identify_image(handle: ModelHandle, image, max_new_tokens: int = 180) -> str:
    """Runs Qwen on one image and returns its raw decoded text response.

    `image` may be a filesystem path (str/Path, for CLI/batch use) or an
    already-loaded PIL.Image (for the API, so uploaded bytes never need to
    touch disk).
    """
    if isinstance(image, Image.Image):
        image_content = {"type": "image", "image": image}
    else:
        image_content = {"type": "image", "url": str(Path(image).resolve())}

    messages = [
        {
            "role": "user",
            "content": [
                image_content,
                {"type": "text", "text": PROMPT},
            ],
        }
    ]

    inputs = handle.processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    ).to(handle.device)
    inputs.pop("token_type_ids", None)

    with torch.inference_mode():
        output = handle.model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
        )

    generated = output[0][inputs["input_ids"].shape[-1]:]
    return handle.processor.decode(generated, skip_special_tokens=True)


def parse_identification(raw_text: str) -> dict:
    """Parses Qwen's raw text into a normalized identification dict.

    Never raises. On malformed/missing JSON, returns all fields as None
    plus a non-None "parse_error" string, so callers can still proceed
    (e.g. route to an "unknown" sorting decision) instead of crashing.
    """
    fields = {key: None for key in IDENTIFICATION_FIELDS}

    match = _JSON_BLOCK_RE.search(raw_text)
    if not match:
        return {**fields, "parse_error": "no JSON object found in model output", "raw": raw_text}

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as e:
        return {**fields, "parse_error": f"invalid JSON: {e}", "raw": raw_text}

    if not isinstance(data, dict):
        return {**fields, "parse_error": "parsed JSON is not an object", "raw": raw_text}

    for key in IDENTIFICATION_FIELDS:
        value = data.get(key)
        if isinstance(value, str) and value.strip().lower() in _NULLISH_STRINGS:
            value = None
        fields[key] = value

    fields["parse_error"] = None
    fields["raw"] = raw_text
    return fields
