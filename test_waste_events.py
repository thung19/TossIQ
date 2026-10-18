"""Tests for the can a disposal event is attributed to.

WASTE_EVENTS.BIN_ID is what makes a can's observed fill countable, so "the
insert attributes an event to the right can, and to no can at all when it
cannot tell" is the property the campus map depends on -- a false attribution
is worse than none, because it reads as observed. db.py opens its own
connection per call, so these tests stand a fake connection in its place
(plain stdlib unittest.mock, no live OCI connection, same style as
test_insights.py) and assert the bind values the INSERT actually receives.
"""

import os
import unittest
from unittest import mock

import db

CAN_IDS = {"VU-RAND-01": 11, "VU-LIBRARY-01": 14}


class FakeVar:
    """Stands in for cursor.var(int)'s RETURNING output bind."""

    def getvalue(self):
        return [7]


class FakeCursor:
    def __init__(self):
        self.lookups = []
        self.insert_binds = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def var(self, _type):
        return FakeVar()

    def execute(self, sql, **binds):
        if "FROM cans" in sql:
            self.lookups.append(binds["can_code"])
            self._row = (CAN_IDS[binds["can_code"]],) if binds["can_code"] in CAN_IDS else None
        else:
            self.insert_binds = binds
            self._row = None

    def fetchone(self):
        return self._row


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.commits += 1


def insert(location=None, bin_id=None):
    cursor = FakeCursor()
    with mock.patch("db.get_connection", return_value=FakeConnection(cursor)):
        db.insert_waste_event(detected_object="aluminum can", location=location, bin_id=bin_id)
    return cursor


class BinIdResolutionTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("LIVE_CAMERA_CAN_CODE", None)

    def test_location_matching_a_can_code_attributes_the_event_to_that_can(self):
        cursor = insert(location="VU-RAND-01")
        self.assertEqual(cursor.insert_binds["bin_id"], 11)

    def test_location_matching_no_can_leaves_the_event_unattributed(self):
        cursor = insert(location="FIRSTMATE-TEST")
        self.assertIsNone(cursor.insert_binds["bin_id"])

    def test_a_configured_live_camera_can_never_claims_an_event_with_no_location(self):
        os.environ["LIVE_CAMERA_CAN_CODE"] = "VU-LIBRARY-01"
        cursor = insert()
        self.assertIsNone(cursor.insert_binds["bin_id"])
        self.assertEqual(cursor.lookups, [])

    def test_a_configured_live_camera_can_never_claims_a_harness_capture(self):
        os.environ["LIVE_CAMERA_CAN_CODE"] = "VU-LIBRARY-01"
        for location in ("FIRSTMATE-TEST", "SKU Verification", "Loading Dock B"):
            with self.subTest(location=location):
                cursor = insert(location=location)
                self.assertIsNone(cursor.insert_binds["bin_id"])
                self.assertEqual(cursor.lookups, [location])

    def test_a_rig_location_resolves_no_can_on_its_own(self):
        os.environ["LIVE_CAMERA_CAN_CODE"] = "VU-LIBRARY-01"
        cursor = insert(location="live-webcam")
        self.assertIsNone(cursor.insert_binds["bin_id"])

    def test_an_explicit_bin_id_is_used_without_a_lookup(self):
        cursor = insert(location="live-webcam", bin_id=99)
        self.assertEqual(cursor.insert_binds["bin_id"], 99)
        self.assertEqual(cursor.lookups, [])

    def test_an_event_with_no_location_is_left_unattributed(self):
        cursor = insert()
        self.assertIsNone(cursor.insert_binds["bin_id"])
        self.assertEqual(cursor.lookups, [])


class CanIdForCodeTests(unittest.TestCase):
    def resolve(self, can_code):
        cursor = FakeCursor()
        with mock.patch("db.get_connection", return_value=FakeConnection(cursor)):
            return db.can_id_for_code(can_code)

    def test_a_registered_code_resolves_to_its_can(self):
        self.assertEqual(self.resolve("VU-LIBRARY-01"), 14)

    def test_an_unregistered_code_resolves_to_no_can(self):
        self.assertIsNone(self.resolve("VU-NOT-A-CAN"))


class CameraServiceAttributionTests(unittest.TestCase):
    """The live rig reports a rig name, not a can code, so it is the one caller
    that names its can through LIVE_CAMERA_CAN_CODE."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("LIVE_CAMERA_CAN_CODE", None)

    def persist(self):
        import camera_service

        detection = {"label": "bottle", "category": "recycling", "confidence": 0.91}
        with mock.patch("db.insert_waste_event") as insert_event, mock.patch(
            "db.can_id_for_code", side_effect=lambda code: CAN_IDS.get(code)
        ):
            camera_service.CameraService()._persist(detection)
        return insert_event

    def test_a_capture_is_attributed_to_the_configured_can(self):
        os.environ["LIVE_CAMERA_CAN_CODE"] = "VU-LIBRARY-01"
        insert_event = self.persist()
        self.assertEqual(insert_event.call_args.kwargs["bin_id"], 14)
        self.assertEqual(insert_event.call_args.kwargs["location"], "live-webcam")

    def test_an_unconfigured_rig_logs_the_capture_unattributed(self):
        insert_event = self.persist()
        self.assertIsNone(insert_event.call_args.kwargs["bin_id"])

    def test_a_configured_code_naming_no_registered_can_attributes_nothing(self):
        os.environ["LIVE_CAMERA_CAN_CODE"] = "VU-NOT-A-CAN"
        insert_event = self.persist()
        self.assertIsNone(insert_event.call_args.kwargs["bin_id"])


if __name__ == "__main__":
    unittest.main()
