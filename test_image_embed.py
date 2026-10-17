"""Unit tests for image_embed.py.

Covers the part testable without a live OCI Generative AI call:
embed_image() never raises -- a simulated API exception is caught, logged,
and reported as None, same graceful-degradation contract as the rest of
this project's OCI integrations (oci_storage.py, genai_vision.py). Live
embedding calls are out of scope here -- the captain verifies that with
real credentials.
"""

import unittest
from unittest import mock

from PIL import Image

import image_embed


class EmbedImageTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (4, 4))
        image_embed._handle = image_embed.EmbedHandle(
            client=mock.Mock(), compartment_id="ocid1.compartment.test", model_id="cohere.embed-v4.0"
        )

    def tearDown(self):
        image_embed._handle = None

    def test_well_formed_response_returns_embedding(self):
        response = mock.Mock()
        response.data.embeddings = [[0.1] * image_embed.EMBEDDING_DIMENSIONS]
        image_embed._handle.client.embed_text.return_value = response

        result = image_embed.embed_image(self.image)

        self.assertEqual(len(result), image_embed.EMBEDDING_DIMENSIONS)
        image_embed._handle.client.embed_text.assert_called_once()

    def test_api_exception_returns_none_without_raising(self):
        image_embed._handle.client.embed_text.side_effect = TimeoutError("request timed out")

        result = image_embed.embed_image(self.image)

        self.assertIsNone(result)

    def test_malformed_response_returns_none_without_raising(self):
        response = mock.Mock()
        response.data.embeddings = []
        image_embed._handle.client.embed_text.return_value = response

        result = image_embed.embed_image(self.image)

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
