"""Unit tests for db.py's update_hazard_status validation logic.

Mocks db.get_connection directly (plain stdlib unittest.mock, no live OCI
connection, same style as test_insights.py) so these run without credentials.
"""

import unittest
from unittest import mock

import db


class UpdateHazardStatusValidationTests(unittest.TestCase):
    @mock.patch("db.get_connection")
    def test_invalid_status_raises_value_error_without_a_live_db_call(self, mock_get_connection):
        with self.assertRaises(ValueError):
            db.update_hazard_status(1, "in_progress")
        mock_get_connection.assert_not_called()

    @mock.patch("db.get_connection")
    def test_valid_statuses_do_not_raise_value_error(self, mock_get_connection):
        cursor = mock.MagicMock()
        cursor.rowcount = 1
        conn = mock.MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        mock_get_connection.return_value.__enter__.return_value = conn

        for status in db.VALID_HAZARD_STATUSES:
            db.update_hazard_status(1, status)


if __name__ == "__main__":
    unittest.main()
