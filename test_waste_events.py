"""Tests for the can a disposal event is attributed to.

WASTE_EVENTS.BIN_ID is what makes a can's observed fill countable, so "the
insert resolves a can" is the property the campus map depends on. db.py opens
its own connection per call, so these tests stand a fake connection in its
place (plain stdlib unittest.mock, no live OCI connection, same style as
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

    def test_live_camera_can_code_attributes_a_rig_location(self):
        os.environ["LIVE_CAMERA_CAN_CODE"] = "VU-LIBRARY-01"
        cursor = insert(location="live-webcam")
        self.assertEqual(cursor.insert_binds["bin_id"], 14)
        self.assertEqual(cursor.lookups, ["live-webcam", "VU-LIBRARY-01"])

    def test_live_camera_can_code_does_not_override_a_resolvable_location(self):
        os.environ["LIVE_CAMERA_CAN_CODE"] = "VU-LIBRARY-01"
        cursor = insert(location="VU-RAND-01")
        self.assertEqual(cursor.insert_binds["bin_id"], 11)

    def test_blank_live_camera_can_code_is_treated_as_unset(self):
        os.environ["LIVE_CAMERA_CAN_CODE"] = "   "
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


if __name__ == "__main__":
    unittest.main()
