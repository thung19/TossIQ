"""Unit tests for asku.py.

Covers the parts testable without a live OCI Generative AI call: assembling
observations from db.py's aggregates, rendering them into the prompt, and
that answer_question() returns the grounding alongside the answer and turns
an OCI failure into an AskuError rather than letting the SDK exception
escape. Live inference is out of scope here -- the captain verifies that
against the real endpoint with real credentials, same split as
test_genai_vision.py.

Every db.py call is stubbed, so no test here touches the OCI Autonomous DB.
"""

import os
import unittest
from unittest import mock

import asku
import db

OVERVIEW = {
    "window_days": 30,
    "total_items": 1030,
    "by_category": [
        {"category": "recycling", "count": 430},
        {"category": "landfill", "count": 346},
        {"category": "compost", "count": 254},
    ],
    "top_items": [
        {"object": "glass bottle", "count": 64},
        {"object": "plastic clamshell", "count": 49},
    ],
    "trend": [
        {"date": "2026-10-16", "count": 171},
        {"date": "2026-10-17", "count": 187},
    ],
}

ITEMS = [
    {
        "detected_object": "glass bottle",
        "matched_product": "Dining Hall Water Bottle",
        "count": 46,
        "last_seen": "2026-10-17 20:30:45",
        "estimated_value": 69.0,
    },
    {
        "detected_object": "plastic clamshell",
        "matched_product": None,
        "count": 49,
        "last_seen": "2026-10-17 21:00:46",
        "estimated_value": None,
    },
]

LOCATIONS = [
    {"location": "VU-ALUMNI-01", "category": "landfill", "count": 9},
    {"location": "VU-ALUMNI-02", "category": "recycling", "count": 10},
]

HAZARD_EVENTS = [
    {
        "detected_object": "lithium battery",
        "location": "Loading Dock B",
        "hazard_reason": "visible battery warning symbol",
        "date": "2026-10-15",
    },
]

RECENT_EVENTS = [
    {
        "event_id": 991,
        "detected_object": "chip bag",
        "material": "plastic",
        "category": "landfill",
        "location": "VU-ALUMNI-01",
        "confidence": 90,
        "image_key": "events/abc.jpg",
        "created_at": "2026-10-17 18:38:31",
        "hazard_flag": 0,
        "hazard_reason": None,
        "visible_text": None,
        "reusable_condition": "depleted",
    },
]

PRODUCTS = [
    {
        "product_id": 21,
        "product_name": "Dining Hall Water Bottle",
        "supplier": "Campus Dining",
        "sku": "BOT-001",
        "material": "plastic",
        "unit_cost": 1.5,
    },
]

EMPTY_OVERVIEW = {
    "window_days": 30,
    "total_items": 0,
    "by_category": [],
    "top_items": [],
    "trend": [],
}


def _patch_db(test, **overrides):
    """Stubs every db.py function collect_observations() reads.

    Defaults are the populated dataset above; pass an override to simulate a
    different one (e.g. overview=EMPTY_OVERVIEW).
    """
    returns = {
        "stats_overview": OVERVIEW,
        "stats_items": ITEMS,
        "stats_locations": LOCATIONS,
        "list_hazard_events": HAZARD_EVENTS,
        "list_recent_events": RECENT_EVENTS,
        "list_products": PRODUCTS,
    }
    aliases = {
        "overview": "stats_overview",
        "items": "stats_items",
        "locations": "stats_locations",
        "hazard_events": "list_hazard_events",
        "recent_events": "list_recent_events",
        "products": "list_products",
    }
    for key, value in overrides.items():
        returns[aliases[key]] = value

    for name, value in returns.items():
        patcher = mock.patch.object(db, name, return_value=value)
        patcher.start()
        test.addCleanup(patcher.stop)


def _make_handle():
    return asku.genai_vision.GenAIHandle(
        client=mock.Mock(),
        compartment_id="ocid1.compartment.test",
        model_id="cohere.command-a-03-2025",
    )


def _chat_response(text: str):
    response = mock.Mock()
    content_item = mock.Mock()
    content_item.text = text
    message = mock.Mock()
    message.content = [content_item]
    response.data.chat_response.message = message
    return response


class CollectObservationsTests(unittest.TestCase):
    def test_reads_the_existing_aggregates_for_the_requested_window(self):
        _patch_db(self)

        observations = asku.collect_observations(days=7)

        self.assertEqual(observations["window_days"], 7)
        self.assertEqual(observations["overview"], OVERVIEW)
        self.assertEqual(observations["items"], ITEMS)
        self.assertEqual(observations["locations"], LOCATIONS)
        self.assertEqual(observations["hazard_events"], HAZARD_EVENTS)
        self.assertEqual(observations["recent_events"], RECENT_EVENTS)
        self.assertEqual(observations["products"], PRODUCTS)

        db.stats_overview.assert_called_once_with(days=7)
        db.stats_items.assert_called_once_with(days=7)
        db.stats_locations.assert_called_once_with(days=7)
        db.list_hazard_events.assert_called_once_with(days=7)
        db.list_recent_events.assert_called_once_with(limit=asku.RECENT_EVENT_LIMIT)
        db.list_products.assert_called_once_with()


class PromptTests(unittest.TestCase):
    def setUp(self):
        _patch_db(self)
        self.observations = asku.collect_observations(days=30)
        self.prompt = asku.build_prompt(self.observations, "Which item do we throw away most?")

    def test_system_prompt_forbids_unsupported_figures_and_generic_advice(self):
        system = self.prompt["system"]
        self.assertIn("ONLY the OBSERVATIONS block", system)
        self.assertIn("Never state a count", system)
        self.assertIn("the recorded data does not show this", system)
        self.assertIn("Never give generic waste-reduction", system)

    def test_prompt_carries_the_question(self):
        self.assertIn("QUESTION: Which item do we throw away most?", self.prompt["user"])

    def test_prompt_carries_the_real_aggregate_values(self):
        user = self.prompt["user"]
        # Totals and category split from db.stats_overview.
        self.assertIn("Total items logged: 1030", user)
        self.assertIn("recycling: 430 items", user)
        self.assertIn("landfill: 346 items", user)
        self.assertIn("compost: 254 items", user)
        # Per-object counts and the daily trend.
        self.assertIn("glass bottle: 64 items", user)
        self.assertIn("2026-10-17: 187 items", user)
        # Catalog match, estimated value, and the catalog entry itself.
        self.assertIn("Dining Hall Water Bottle", user)
        self.assertIn("$69.00", user)
        self.assertIn("unit cost $1.50", user)
        # Locations, hazards, and recent events.
        self.assertIn("VU-ALUMNI-01 / landfill: 9 items", user)
        self.assertIn("visible battery warning symbol", user)
        self.assertIn("'chip bag'", user)

    def test_catalog_section_labels_matched_counts_as_a_portion_not_a_total(self):
        # db.stats_items() groups by (object, product), so "glass bottle" is
        # 46 there but 64 in the per-object totals. The matched row has to
        # read as a portion of that object, or the model sees two totals.
        user = self.prompt["user"]
        self.assertIn("'Dining Hall Water Bottle': 46 of its items", user)

    def test_unmatched_item_is_not_rendered_as_a_catalog_match(self):
        self.assertNotIn("plastic clamshell matched to catalog product", self.prompt["user"])

    def test_grounding_sections_mirror_the_prompt_text(self):
        user = self.prompt["user"]
        for section in asku.observation_sections(self.observations):
            self.assertIn(section["title"], user)
            for line in section["lines"]:
                self.assertIn(line, user)

    def test_window_is_stated_in_the_observations(self):
        self.assertIn("last 30 days", self.prompt["user"])


class EmptyDatasetPromptTests(unittest.TestCase):
    """An empty dataset must produce a prompt that cannot be answered with
    invented figures -- not a silently empty context."""

    def setUp(self):
        _patch_db(
            self,
            overview=EMPTY_OVERVIEW,
            items=[],
            locations=[],
            hazard_events=[],
            recent_events=[],
            products=[],
        )
        self.observations = asku.collect_observations(days=30)
        self.prompt = asku.build_prompt(self.observations, "How many bottles did we recycle?")

    def test_prompt_states_that_nothing_is_recorded(self):
        self.assertIn(asku.NO_OBSERVATIONS_NOTICE, self.prompt["user"])

    def test_every_section_states_its_emptiness_explicitly(self):
        for section in asku.observation_sections(self.observations):
            self.assertTrue(section["lines"], f"section {section['title']!r} rendered no lines")
            for line in section["lines"]:
                self.assertIn(line, self.prompt["user"])

        user = self.prompt["user"]
        self.assertIn("(no identified items recorded in this window)", user)
        self.assertIn("(no days with recorded disposals in this window)", user)
        self.assertIn("(no logged item was matched to a catalog product in this window)", user)
        self.assertIn("(no disposals recorded against any location in this window)", user)
        self.assertIn("(no hazard-flagged events recorded in this window)", user)
        self.assertIn("(no events have ever been logged)", user)
        self.assertIn("(no products are registered in the organization's catalog)", user)

    def test_no_populated_figures_leak_into_an_empty_prompt(self):
        user = self.prompt["user"]
        self.assertIn("Total items logged: 0", user)
        for figure in ("1030", "430", "glass bottle", "Dining Hall Water Bottle", "$69.00"):
            self.assertNotIn(figure, user)


class CappingTests(unittest.TestCase):
    def test_long_sections_are_truncated_with_the_full_row_count_stated(self):
        locations = [
            {"location": f"BIN-{i:02d}", "category": "recycling", "count": i}
            for i in range(asku.MAX_LOCATION_ROWS + 5)
        ]
        _patch_db(self, locations=locations)

        observations = asku.collect_observations(days=30)
        lines = asku.observation_sections(observations)[4]["lines"]

        self.assertEqual(len(lines), asku.MAX_LOCATION_ROWS + 1)
        self.assertEqual(
            lines[-1],
            f"(showing the first {asku.MAX_LOCATION_ROWS} of {len(locations)} rows)",
        )


class AnswerQuestionTests(unittest.TestCase):
    def setUp(self):
        _patch_db(self)
        self.handle = _make_handle()

    def test_returns_answer_with_the_grounding_it_was_produced_from(self):
        self.handle.client.chat.return_value = _chat_response(
            "  Glass bottles, at 64 items observed.  "
        )

        result = asku.answer_question("What is discarded most?", days=30, handle=self.handle)

        self.assertEqual(result["answer"], "Glass bottles, at 64 items observed.")
        self.assertEqual(result["question"], "What is discarded most?")
        self.assertEqual(result["window_days"], 30)
        self.assertEqual(result["model_id"], "cohere.command-a-03-2025")
        self.assertEqual(
            result["grounding"],
            asku.observation_sections(asku.collect_observations(days=30)),
        )

    def test_the_model_is_sent_the_observations_and_the_question(self):
        self.handle.client.chat.return_value = _chat_response("ok")

        asku.answer_question("What is discarded most?", days=30, handle=self.handle)

        self.handle.client.chat.assert_called_once()
        chat_details = self.handle.client.chat.call_args.args[0]
        self.assertEqual(chat_details.serving_mode.model_id, "cohere.command-a-03-2025")
        system, user = chat_details.chat_request.messages
        self.assertIn("ONLY the OBSERVATIONS block", system.content[0].text)
        self.assertIn("Total items logged: 1030", user.content[0].text)
        self.assertIn("QUESTION: What is discarded most?", user.content[0].text)

    def test_oci_failure_becomes_an_askuerror(self):
        self.handle.client.chat.side_effect = TimeoutError("request timed out")

        with self.assertRaises(asku.AskuError) as caught:
            asku.answer_question("What is discarded most?", handle=self.handle)

        self.assertIn("OCI Generative AI request failed", str(caught.exception))

    def test_response_without_answer_text_becomes_an_askuerror(self):
        response = mock.Mock()
        response.data.chat_response.message.content = []
        self.handle.client.chat.return_value = response

        with self.assertRaises(asku.AskuError) as caught:
            asku.answer_question("What is discarded most?", handle=self.handle)

        self.assertIn("no answer text", str(caught.exception))


class AnalyticsFailureTests(unittest.TestCase):
    def test_database_failure_becomes_an_askuerror(self):
        patcher = mock.patch.object(db, "stats_overview", side_effect=RuntimeError("DB down"))
        patcher.start()
        self.addCleanup(patcher.stop)

        with self.assertRaises(asku.AskuError) as caught:
            asku.answer_question("What is discarded most?", handle=_make_handle())

        self.assertIn("Could not read analytics", str(caught.exception))


class LoadChatHandleTests(unittest.TestCase):
    def test_reuses_the_vision_clients_auth_with_the_chat_model_id(self):
        base = _make_handle()
        base.model_id = "cohere.command-a-vision"
        with mock.patch.object(asku.genai_vision, "load_model", return_value=base), \
                mock.patch.dict("os.environ", {"OCI_GENAI_CHAT_MODEL_ID": "cohere.command-a-03-2025"}):
            handle = asku.load_chat_handle()

        self.assertIs(handle.client, base.client)
        self.assertEqual(handle.compartment_id, base.compartment_id)
        self.assertEqual(handle.model_id, "cohere.command-a-03-2025")

    def test_falls_back_to_the_default_chat_model_not_the_vision_model(self):
        base = _make_handle()
        base.model_id = "cohere.command-a-vision"
        env = {k: v for k, v in os.environ.items() if k != "OCI_GENAI_CHAT_MODEL_ID"}
        with mock.patch.object(asku.genai_vision, "load_model", return_value=base), \
                mock.patch.dict("os.environ", env, clear=True):
            handle = asku.load_chat_handle()

        self.assertEqual(handle.model_id, asku.DEFAULT_CHAT_MODEL_ID)
        self.assertNotEqual(handle.model_id, "cohere.command-a-vision")


if __name__ == "__main__":
    unittest.main()
