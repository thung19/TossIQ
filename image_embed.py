"""Cohere Embed v4 (via OCI Generative AI) image embeddings for visual SKU
matching.

Structured in parallel to genai_vision.py: non-secret request config
(region, compartment, model id) comes from `.env` via `load_dotenv()`, same
pattern as the rest of this project's OCI integrations. Auth is the same
standard OCI config file (`oci.config.from_file()`, default `~/.oci/config`)
genai_vision.py already uses -- this module never reads or requires its own
`.env`-based OCI Generative AI credential.

`cohere.embed-v4.0` is command-a-vision's sibling embedding model on the
same OCI Generative AI service. The SDK method is named `embed_text()` even
when embedding an image -- `EmbedTextDetails.inputs` just takes a base64
`data:image/...;base64,...` URL instead of plain text when `input_type`
is "IMAGE", the same data-URL encoding approach genai_vision.py and
oci_storage.py already use for images.
"""

import logging
import os
from io import BytesIO

import oci
from oci.generative_ai_inference import GenerativeAiInferenceClient
from oci.generative_ai_inference.models import EmbedTextDetails, OnDemandServingMode
from dotenv import load_dotenv
from PIL import Image
import base64

load_dotenv()

logger = logging.getLogger("tossiq")

DEFAULT_REGION = "us-chicago-1"
DEFAULT_EMBED_MODEL_ID = "cohere.embed-v4.0"

EMBEDDING_DIMENSIONS = 1536


class EmbedHandle:
    """Bundles the OCI Generative AI client and the request-shaping config."""

    def __init__(self, client, compartment_id, model_id):
        self.client = client
        self.compartment_id = compartment_id
        self.model_id = model_id


def load_embed_model() -> EmbedHandle:
    """Builds an EmbedHandle from the standard OCI config file plus the
    non-secret request config read from `.env` (region/compartment/model).

    Reuses the same env vars genai_vision.py reads for region/compartment/
    config profile (OCI_GENAI_REGION / OCI_GENAI_COMPARTMENT_ID /
    OCI_GENAI_CONFIG_PROFILE) -- both models live on the same OCI
    Generative AI service and compartment -- with its own model id env var
    (OCI_GENAI_EMBED_MODEL_ID) so the chat and embedding models can be
    swapped independently.
    """
    region = os.environ.get("OCI_GENAI_REGION", DEFAULT_REGION)
    compartment_id = os.environ.get("OCI_GENAI_COMPARTMENT_ID")
    model_id = os.environ.get("OCI_GENAI_EMBED_MODEL_ID", DEFAULT_EMBED_MODEL_ID)
    config_profile = os.environ.get("OCI_GENAI_CONFIG_PROFILE", "DEFAULT")

    config = oci.config.from_file(profile_name=config_profile)
    client = GenerativeAiInferenceClient(
        config=config,
        service_endpoint=f"https://inference.generativeai.{region}.oci.oraclecloud.com",
    )
    return EmbedHandle(client, compartment_id, model_id)


def _image_to_data_url(image: Image.Image) -> str:
    """Encodes a PIL.Image as a base64 data: URL -- same approach
    genai_vision.py's _image_to_data_url() uses for Cohere's chat API."""
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="JPEG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


_handle: EmbedHandle | None = None


def embed_image(image: Image.Image) -> list[float] | None:
    """Embeds a PIL.Image with Cohere Embed v4 (via OCI Generative AI),
    returning the 1536-dim embedding as a list of floats.

    Never raises: any OCI/API error (auth failure, timeout, rate limit,
    malformed response) is caught, logged, and reported as None instead --
    same graceful-degradation posture as the rest of this project's OCI
    integrations (oci_storage.py, genai_vision.py) -- so a failed embedding
    never crashes the calling flow (catalog upload or disposal-event
    persistence).
    """
    global _handle
    try:
        if _handle is None:
            _handle = load_embed_model()

        embed_details = EmbedTextDetails(
            compartment_id=_handle.compartment_id,
            serving_mode=OnDemandServingMode(model_id=_handle.model_id),
            inputs=[_image_to_data_url(image)],
            input_type="IMAGE",
            truncate="NONE",
        )
        response = _handle.client.embed_text(embed_details)
        return list(response.data.embeddings[0])
    except Exception:
        logger.exception("OCI Generative AI image embedding request failed")
        return None
