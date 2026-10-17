"""Unit tests for genai_vision.py.

Covers the parts testable without a live OCI Generative AI call: parsing
raw model output into the identification dict, and that identify_image()
never raises -- it always returns a parse_error-populated dict on a
malformed response or a simulated API exception, same contract as
identify.py's parse_identification(). Live inference is out of scope here
-- the captain verifies that with real credentials.
"""

import unittest
from unittest import mock

from PIL import Image

import genai_vision

WELL_FORMED_JSON = """
{
  "object": "plastic water bottle",
  "material": "plastic",
  "material_subtype": "PET",
  "food_contaminated": false,
  "hazard_flag": false,
  "hazard_reason": null,
  "visible_text": "Aqua Pure",
  "reusable_condition": "intact"
}
"""


def _make_handle():
    return genai_vision.GenAIHandle(client=mock.Mock(), compartment_id="ocid1.compartment.test", model_id="cohere.command-a-vision")


def _chat_response(text: str):
    response = mock.Mock()
    content_item = mock.Mock()
    content_item.text = text
    message = mock.Mock()
    message.content = [content_item]
    response.data.chat_response.message = message
    return response


class ParseIdentificationTests(unittest.TestCase):
    def test_well_formed_json(self):
        result = genai_vision.parse_identification(WELL_FORMED_JSON)
        self.assertIsNone(result["parse_error"])
        self.assertEqual(result["object"], "plastic water bottle")
        self.assertEqual(result["material"], "plastic")
        self.assertEqual(result["material_subtype"], "PET")
        self.assertIs(result["food_contaminated"], False)
        self.assertIs(result["hazard_flag"], False)
        self.assertIsNone(result["hazard_reason"])
        self.assertEqual(result["visible_text"], "Aqua Pure")
        self.assertEqual(result["reusable_condition"], "intact")

    def test_no_json_object_found(self):
        result = genai_vision.parse_identification("I cannot identify this item.")
        self.assertEqual(result["parse_error"], "no JSON object found in model output")
        for key in genai_vision.IDENTIFICATION_FIELDS:
            self.assertIsNone(result[key])

    def test_malformed_json(self):
        result = genai_vision.parse_identification('{"object": "bottle", "material": }')
        self.assertIn("invalid JSON", result["parse_error"])

    def test_nullish_string_normalized_to_none(self):
        raw = (
            '{"object": "unknown", "material": "n/a", "material_subtype": null, '
            '"food_contaminated": "none", "hazard_flag": "unknown", "hazard_reason": "",'
            ' "visible_text": "n/a", "reusable_condition": "None"}'
        )
        result = genai_vision.parse_identification(raw)
        self.assertIsNone(result["object"])
        self.assertIsNone(result["material"])
        self.assertIsNone(result["material_subtype"])
        self.assertIsNone(result["food_contaminated"])
        self.assertIsNone(result["hazard_flag"])
        self.assertIsNone(result["hazard_reason"])
        self.assertIsNone(result["visible_text"])
        self.assertIsNone(result["reusable_condition"])
        self.assertIsNone(result["parse_error"])


class IdentifyImageTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (4, 4))

    def test_well_formed_response(self):
        handle = _make_handle()
        handle.client.chat.return_value = _chat_response(WELL_FORMED_JSON)

        result = genai_vision.identify_image(handle, self.image)

        self.assertIsNone(result["parse_error"])
        self.assertEqual(result["object"], "plastic water bottle")
        handle.client.chat.assert_called_once()

    def test_malformed_response_returns_parse_error_without_raising(self):
        handle = _make_handle()
        handle.client.chat.return_value = _chat_response("not valid json at all")

        result = genai_vision.identify_image(handle, self.image)

        self.assertIsNotNone(result["parse_error"])
        for key in genai_vision.IDENTIFICATION_FIELDS:
            self.assertIsNone(result[key])

    def test_api_exception_returns_parse_error_without_raising(self):
        handle = _make_handle()
        handle.client.chat.side_effect = TimeoutError("request timed out")

        result = genai_vision.identify_image(handle, self.image)

        self.assertIn("OCI Generative AI request failed", result["parse_error"])
        self.assertIsNone(result["raw"])
        for key in genai_vision.IDENTIFICATION_FIELDS:
            self.assertIsNone(result[key])


if __name__ == "__main__":
    unittest.main()
