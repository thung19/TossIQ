"""Rules engine that turns a Qwen identification into a disposal decision.

Deliberately separate from the model: disposal rules vary by city/hauler,
so they live in rules.json (editable without touching code) rather than
being hardcoded here. Rules are tried in order; the first whole match wins.
"""

import json
from pathlib import Path

DEFAULT_RULES_PATH = Path(__file__).with_name("rules.json")

CATEGORIES = {"recycling", "compost", "landfill", "unknown"}


def load_rules(path=DEFAULT_RULES_PATH) -> list:
    with open(path) as f:
        rules = json.load(f)["rules"]
    for rule in rules:
        if rule["category"] not in CATEGORIES:
            raise ValueError(f"rule {rule['name']!r} has invalid category {rule['category']!r}")
    return rules


def _normalize(value):
    return value.strip().lower() if isinstance(value, str) else value


def _matches(identification: dict, conditions: dict) -> bool:
    for key, expected in conditions.items():
        if key == "object_keywords":
            text = _normalize(identification.get("object")) or ""
            if not any(_normalize(kw) in text for kw in expected):
                return False
            continue

        actual = _normalize(identification.get(key))
        expected_values = expected if isinstance(expected, list) else [expected]
        expected_values = [_normalize(v) for v in expected_values]
        if actual not in expected_values:
            return False
    return True


def classify(identification: dict, rules=None) -> dict:
    """Returns {"category", "reason", "matched_rule"} for an identification dict.

    Falls back to "unknown" (never raises) when no rule matches, so a gap
    in the rules config degrades gracefully instead of breaking the pipeline.
    """
    if rules is None:
        rules = load_rules()

    for rule in rules:
        if _matches(identification, rule["match"]):
            return {
                "category": rule["category"],
                "reason": rule["reason"],
                "matched_rule": rule["name"],
            }

    return {
        "category": "unknown",
        "reason": "No disposal rule matched the identified object/material.",
        "matched_rule": None,
    }
