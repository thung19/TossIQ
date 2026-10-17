"""Batch-tests main.run() against labeled images and reports identification
accuracy (did the model name the right object?) and sorting accuracy (did
the rules engine land on the right bin?) as separate numbers -- a bad score
can come from either the model or the rules, and this tells you which.

Usage:
    python evaluate.py                  # uses images/labels.json
    python evaluate.py path/to/labels.json
"""

import json
import sys
from pathlib import Path

from sorting import load_rules
from main import run

IMAGES_DIR = Path("images")
DEFAULT_LABELS_PATH = IMAGES_DIR / "labels.json"


def load_labels(path) -> dict:
    with open(path) as f:
        return json.load(f)


def object_matches(identified_object, expected_keywords) -> bool:
    if not identified_object:
        return False
    text = identified_object.lower()
    return any(kw.lower() in text for kw in expected_keywords)


def main():
    labels_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LABELS_PATH
    labels = load_labels(labels_path)

    rules = load_rules()

    id_correct = 0
    sort_correct = 0
    total = 0

    for filename, expected in labels.items():
        image_path = IMAGES_DIR / filename
        if not image_path.exists():
            print(f"skip {filename}: file not found")
            continue

        result = run(image_path, rules=rules)
        identification = result["identification"]
        sorting = result["sorting"]

        is_id_correct = object_matches(identification.get("object"), expected["expected_object_keywords"])
        is_sort_correct = sorting["category"] == expected["expected_category"]

        id_correct += is_id_correct
        sort_correct += is_sort_correct
        total += 1

        print(f"\n{filename}")
        print(
            f"  identified object: {identification.get('object')!r} "
            f"-> {'OK' if is_id_correct else 'MISS'} "
            f"(expected one of {expected['expected_object_keywords']})"
        )
        print(
            f"  sorted category:   {sorting['category']!r} "
            f"-> {'OK' if is_sort_correct else 'MISS'} "
            f"(expected {expected['expected_category']!r}, rule={sorting['matched_rule']})"
        )
        if identification.get("parse_error"):
            print(f"  parse_error: {identification['parse_error']}")

    print()
    if total:
        print(f"Identification accuracy: {id_correct}/{total} ({id_correct / total:.0%})")
        print(f"Sorting accuracy:        {sort_correct}/{total} ({sort_correct / total:.0%})")
    else:
        print("No labeled images found to evaluate.")


if __name__ == "__main__":
    main()
