"""Unit tests for oci_storage.py.

Covers the parts testable without live OCI credentials: the env-var-missing
graceful-skip path, and that the S3 client is constructed with the payload
signing workaround OCI's S3-compat endpoint requires. Live upload behavior
is out of scope here -- the captain verifies that with real credentials.
"""

import unittest
from unittest import mock

import oci_storage

ALL_ENV_VARS = {
    "OCI_OS_NAMESPACE": "ns",
    "OCI_OS_BUCKET": "bucket",
    "OCI_OS_REGION": "us-ashburn-1",
    "OCI_OS_ACCESS_KEY": "key",
    "OCI_OS_SECRET_KEY": "secret",
}


class LoadConfigTests(unittest.TestCase):
    def test_returns_none_when_all_vars_missing(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(oci_storage._load_config())

    def test_returns_none_when_one_var_missing(self):
        partial = dict(ALL_ENV_VARS)
        del partial["OCI_OS_SECRET_KEY"]
        with mock.patch.dict("os.environ", partial, clear=True):
            self.assertIsNone(oci_storage._load_config())

    def test_returns_config_when_all_vars_present(self):
        with mock.patch.dict("os.environ", ALL_ENV_VARS, clear=True):
            self.assertEqual(oci_storage._load_config(), ALL_ENV_VARS)


class UploadImageTests(unittest.TestCase):
    def test_skips_gracefully_when_not_configured(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            result = oci_storage.upload_image(b"fake-jpeg-bytes", "events/test.jpg")
        self.assertIsNone(result)


class GetPresignedUrlTests(unittest.TestCase):
    def test_skips_gracefully_when_not_configured(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            result = oci_storage.get_presigned_url("events/test.jpg")
        self.assertIsNone(result)


class ClientConfigTests(unittest.TestCase):
    def setUp(self):
        oci_storage._clients.clear()
        self.addCleanup(oci_storage._clients.clear)

    def test_endpoint_and_payload_signing_workaround(self):
        with mock.patch("boto3.client") as mock_client:
            oci_storage._client(ALL_ENV_VARS)

        mock_client.assert_called_once()
        _, kwargs = mock_client.call_args
        self.assertEqual(
            kwargs["endpoint_url"],
            "https://ns.compat.objectstorage.us-ashburn-1.oraclecloud.com",
        )
        config = kwargs["config"]
        self.assertEqual(config.s3["payload_signing_enabled"], False)
        self.assertEqual(config.request_checksum_calculation, "when_required")
        self.assertEqual(config.response_checksum_validation, "when_required")


class ClientReuseTests(unittest.TestCase):
    """Presigning many keys -- one dashboard request presigns a URL per row --
    must not construct a boto3 client per key."""

    def setUp(self):
        oci_storage._clients.clear()
        self.addCleanup(oci_storage._clients.clear)

    def test_many_presigned_urls_share_one_client(self):
        with (
            mock.patch.dict("os.environ", ALL_ENV_VARS, clear=True),
            mock.patch("boto3.client") as mock_client,
        ):
            urls = [oci_storage.get_presigned_url(f"events/{n}.jpg") for n in range(3)]

        self.assertEqual(mock_client.call_count, 1)
        self.assertEqual(mock_client.return_value.generate_presigned_url.call_count, 3)
        self.assertEqual(len(urls), 3)

    def test_changed_credentials_build_a_new_client(self):
        rotated = dict(ALL_ENV_VARS, OCI_OS_SECRET_KEY="rotated")
        with mock.patch("boto3.client") as mock_client:
            with mock.patch.dict("os.environ", ALL_ENV_VARS, clear=True):
                oci_storage.get_presigned_url("events/1.jpg")
            with mock.patch.dict("os.environ", rotated, clear=True):
                oci_storage.get_presigned_url("events/1.jpg")

        self.assertEqual(mock_client.call_count, 2)


if __name__ == "__main__":
    unittest.main()
