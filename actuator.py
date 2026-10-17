"""Physical sort-mechanism trigger.

Isolated so real GPIO/motor control can replace the body here later without
touching any caller. There is no hardware to wire yet, so this only logs.
"""

import logging

logger = logging.getLogger("tossiq")


def trigger_sort_mechanism(category: str) -> None:
    logger.info("Triggering sort mechanism for category: %s", category)
