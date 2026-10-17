import json
import sys
from pathlib import Path

import genai_vision
from identify import load_model
from sorting import classify, load_rules

DEFAULT_IMAGE = Path("images/test.jpg")

# Advanced-analysis backend handle, lazily loaded and cached here: `handle`
# stays a parameter for backward compatibility with callers (api.py still
# loads and passes identify.py's Qwen ModelHandle), but the advanced-
# analysis step now runs on genai_vision's own OCI Generative AI client,
# which this module manages independently of that parameter.
_genai_handle = None


def run(image_path, handle=None, rules=None) -> dict:
    """Runs identification + sorting on one image. Reusable by evaluate.py
    so a single loaded model/ruleset can be shared across many images."""
    global _genai_handle
    if _genai_handle is None:
        _genai_handle = genai_vision.load_model()
    if rules is None:
        rules = load_rules()

    identification = genai_vision.identify_image(_genai_handle, image_path)

    if identification["parse_error"]:
        # Malformed model output: still return a usable result instead of
        # crashing the pipeline -- route it to "unknown" for manual review.
        sorting_result = {
            "category": "unknown",
            "reason": f"Could not parse model output: {identification['parse_error']}",
            "matched_rule": None,
        }
    else:
        sorting_result = classify(identification, rules)

    return {"identification": identification, "sorting": sorting_result}


def main():
    image_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_IMAGE

    handle = load_model()
    print(f"Classifying {image_path}...")
    result = run(image_path, handle=handle)

    print("\nIdentification:")
    print(json.dumps(result["identification"], indent=2))

    print("\nSorting decision:")
    print(json.dumps(result["sorting"], indent=2))


if __name__ == "__main__":
    main()
