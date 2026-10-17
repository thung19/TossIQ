"""Cohere Command A Vision (via OCI Generative AI) waste-item identification.

Structured in parallel to oci_storage.py: non-secret request config (region,
compartment, model id) comes from `.env` via `load_dotenv()`, same pattern
as the rest of this project's OCI integrations. Auth for the actual OCI SDK
call is different, though: `GenerativeAiInferenceClient` authenticates via
the standard OCI config file (`oci.config.from_file()`, default
`~/.oci/config`), not an env-var credential like the DB wallet or Object
Storage keys -- that file is already set up and working, so this module
never reads or requires its own `.env`-based OCI Generative AI credential.

Cohere, not Gemini: this tenancy's Generative AI free-trial allows Cohere
models on demand with no rate limit; Gemini and Grok are both capped at
0 tokens/minute tenancy-wide until the account is upgraded (confirmed live
via the OCI Limits API and a live 429 from Gemini), matching what OCI's own
hackathon starter kit documents ("For the Free Trial, use the Cohere
model... Grok is not supported in the Free Trial"). Cohere's multimodal
chat API uses its own V2 request/message/content classes (CohereChatRequestV2
etc.), not the generic ChatDetails shape Gemini/Grok/Llama share -- that is
why this module's request construction looks different from a
Gemini-targeting version.

Returns the identification dict in the exact shape identify.py's
parse_identification() does, so sorting.py's classify() and main.py's
run() work unchanged regardless of which vision backend is wired in --
the model is swapped, not the contract with the rest of the pipeline.
"""

import json
import logging
import os
import re
from io import BytesIO

import oci
from oci.generative_ai_inference import GenerativeAiInferenceClient
from oci.generative_ai_inference.models import (
    ChatDetails,
    CohereChatRequestV2,
    CohereImageContentV2,
    CohereImageUrlV2,
    CohereResponseJsonFormat,
    CohereTextContentV2,
    CohereUserMessageV2,
    OnDemandServingMode,
)
from dotenv import load_dotenv
from PIL import Image
import base64

load_dotenv()

logger = logging.getLogger("tossiq")

DEFAULT_REGION = "us-chicago-1"
DEFAULT_MODEL_ID = "cohere.command-a-vision"

# Same prompt text and "return ONLY valid JSON" contract as identify.py's
# PROMPT -- the model backing advanced analysis is swapped, not the
# contract sorting.py's classify() relies on.
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


class GenAIHandle:
    """Bundles the OCI Generative AI client and the request-shaping config."""

    def __init__(self, client, compartment_id, model_id):
        self.client = client
        self.compartment_id = compartment_id
        self.model_id = model_id


def load_model() -> GenAIHandle:
    """Builds a GenAIHandle from the standard OCI config file plus the
    non-secret request config read from `.env` (region/compartment/model)."""
    region = os.environ.get("OCI_GENAI_REGION", DEFAULT_REGION)
    compartment_id = os.environ.get("OCI_GENAI_COMPARTMENT_ID")
    model_id = os.environ.get("OCI_GENAI_MODEL_ID", DEFAULT_MODEL_ID)
    config_profile = os.environ.get("OCI_GENAI_CONFIG_PROFILE", "DEFAULT")

    config = oci.config.from_file(profile_name=config_profile)
    client = GenerativeAiInferenceClient(
        config=config,
        service_endpoint=f"https://inference.generativeai.{region}.oci.oraclecloud.com",
    )
    return GenAIHandle(client, compartment_id, model_id)


def _image_to_data_url(image: Image.Image) -> str:
    """Encodes a PIL.Image as a base64 data: URL -- Cohere's multimodal
    content takes an image as a URL and accepts a data: URL the same way
    it accepts an http(s) one, so the image never needs to touch disk or
    a public endpoint."""
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def parse_identification(raw_text: str) -> dict:
    """Parses the model's raw text into a normalized identification dict.

    Mirrors identify.py's parse_identification(): never raises, and on
    malformed/missing JSON returns all fields as None plus a non-None
    "parse_error" string, so callers can still proceed (e.g. route to an
    "unknown" sorting decision) instead of crashing.
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


def identify_image(handle: GenAIHandle, image) -> dict:
    """Runs Cohere Command A Vision (via OCI Generative AI) on one image and
    returns a parsed identification dict with the same shape identify.py's
    parse_identification() returns.

    `image` may be a filesystem path (str/Path) or an already-loaded
    PIL.Image, same as identify.py's identify_image().

    Never raises: any OCI/API error (auth failure, timeout, rate limit,
    malformed response) is caught and reported as a parse_error-populated
    dict instead, so main.py's run() keeps working exactly as it does
    today for a failed/uncertain identification.
    """
    fields = {key: None for key in IDENTIFICATION_FIELDS}

    try:
        pil_image = image if isinstance(image, Image.Image) else Image.open(image)

        chat_request = CohereChatRequestV2(
            messages=[
                CohereUserMessageV2(
                    content=[
                        CohereTextContentV2(text=PROMPT),
                        CohereImageContentV2(image_url=CohereImageUrlV2(url=_image_to_data_url(pil_image))),
                    ]
                )
            ],
            max_tokens=600,
            temperature=0,
            response_format=CohereResponseJsonFormat(),
        )
        chat_details = ChatDetails(
            compartment_id=handle.compartment_id,
            serving_mode=OnDemandServingMode(model_id=handle.model_id),
            chat_request=chat_request,
        )

        response = handle.client.chat(chat_details)
        raw_text = response.data.chat_response.message.content[0].text
    except Exception as e:
        logger.exception("OCI Generative AI chat request failed")
        return {**fields, "parse_error": f"OCI Generative AI request failed: {e}", "raw": None}

    return parse_identification(raw_text)
