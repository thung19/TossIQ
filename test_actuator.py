"""Unit tests for actuator.py.

There is no physical hardware to wire yet, so trigger_sort_mechanism only
logs; this just confirms it logs and never raises.
"""

import unittest

import actuator


class TriggerSortMechanismTests(unittest.TestCase):
    def test_logs_the_category(self):
        with self.assertLogs("tossiq", level="INFO") as captured:
            actuator.trigger_sort_mechanism("recycling")
        self.assertTrue(any("recycling" in message for message in captured.output))

    def test_does_not_raise(self):
        actuator.trigger_sort_mechanism("unknown")


if __name__ == "__main__":
    unittest.main()
