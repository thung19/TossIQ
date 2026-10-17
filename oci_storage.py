"""OCI Object Storage access layer for TossIQ, via its S3-compatible API.

Thin wrapper around boto3, kept deliberately degraded-by-default: per this
project's design principle that advanced/cloud features degrade gracefully
rather than breaking the core pipeline (see identify.py/sorting.py's "never
raises" pattern), a missing/unset config env var means image upload is
skipped -- logged, not raised -- rather than failing the disposal pipeline.
"""

import logging
import os

import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("tossiq")

_ENV_VARS = (
    "OCI_OS_NAMESPACE",
    "OCI_OS_BUCKET",
    "OCI_OS_REGION",
    "OCI_OS_ACCESS_KEY",
    "OCI_OS_SECRET_KEY",
)


def _load_config() -> dict | None:
    values = {name: os.environ.get(name) for name in _ENV_VARS}
    missing = [name for name, value in values.items() if not value]
    if missing:
        logger.info("OCI Object Storage not configured, missing env vars: %s", ", ".join(missing))
        return None
    return values


def _client(config: dict):
    endpoint_url = f"https://{config['OCI_OS_NAMESPACE']}.compat.objectstorage.{config['OCI_OS_REGION']}.oraclecloud.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=config["OCI_OS_REGION"],
        aws_access_key_id=config["OCI_OS_ACCESS_KEY"],
        aws_secret_access_key=config["OCI_OS_SECRET_KEY"],
        # OCI's S3-compat layer rejects botocore's default chunked/streaming
        # payload signing with "(NotImplemented) AWS chunked encoding not
        # supported" -- this config is required, not optional.
        config=Config(
            s3={"payload_signing_enabled": False},
            request_checksum_calculation="when_required",
            response_checksum_validation="when_required",
        ),
    )


def upload_image(image_bytes: bytes, key: str) -> str | None:
    """Uploads image bytes to OCI Object Storage. Returns the key on success,
    or None if upload was skipped (not configured) or failed -- never raises.
    """
    config = _load_config()
    if config is None:
        return None

    try:
        client = _client(config)
        client.put_object(
            Bucket=config["OCI_OS_BUCKET"],
            Key=key,
            Body=image_bytes,
            ContentType="image/jpeg",
        )
        return key
    except Exception:
        logger.exception("OCI Object Storage upload failed for key %s", key)
        return None


def get_presigned_url(key: str, expires_in: int = 300) -> str | None:
    """Returns a presigned GET URL for `key`, or None if not configured or
    generation failed -- never raises.
    """
    config = _load_config()
    if config is None:
        return None

    try:
        client = _client(config)
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": config["OCI_OS_BUCKET"], "Key": key},
            ExpiresIn=expires_in,
        )
    except Exception:
        logger.exception("OCI Object Storage presigned URL generation failed for key %s", key)
        return None
