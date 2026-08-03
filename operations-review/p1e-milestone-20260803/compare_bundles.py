"""Compare two bundle artifact sets, ignoring the documented clock-derived fields.

`generated_at`, `reference_at` and `valuation_date` are build timestamps -- `docs/STATE.md`
records `reference_at` as "the build time and is never conflated with either". Artifact
hashes recorded inside `bundle_manifest.json` are derived from files that contain those
timestamps, so they move with them. Everything else must be byte-identical.

Usage: python compare_bundles.py <dir_a> <dir_b>
Exit 0 when the two sets agree on content, 1 otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CLOCK_KEYS = {"generated_at", "reference_at", "valuation_date", "bundle_generated_at",
              "exported_at", "built_at"}
#: Hashes of artifacts whose own content carries a timestamp, so they move with the clock.
DERIVED_HASH_PATHS = ("sha256", "bundle_sha256")

ARTIFACTS = ("analysis_bundle.json", "focus_extract.json", "bundle_manifest.json")


def normalize(value, path=""):
    if isinstance(value, dict):
        return {key: normalize(item, f"{path}.{key}")
                for key, item in sorted(value.items())
                if key not in CLOCK_KEYS and key not in DERIVED_HASH_PATHS}
    if isinstance(value, list):
        return [normalize(item, f"{path}[{index}]") for index, item in enumerate(value)]
    return value


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    left, right = Path(argv[1]), Path(argv[2])
    failures = 0
    for name in ARTIFACTS:
        a, b = left / name, right / name
        if not a.is_file() or not b.is_file():
            print(f"SKIP       {name} (missing on one side)")
            continue
        na = normalize(json.loads(a.read_text(encoding="utf-8")))
        nb = normalize(json.loads(b.read_text(encoding="utf-8")))
        if na == nb:
            print(f"IDENTICAL  {name} (content, ignoring clock fields)")
        else:
            failures += 1
            print(f"DIFFERS    {name}")
            _report(na, nb)
    return 1 if failures else 0


def _report(a, b, path="", shown=None):
    shown = shown if shown is not None else []
    if len(shown) >= 15:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                _report(a.get(key), b.get(key), f"{path}.{key}", shown)
        return
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for index, (x, y) in enumerate(zip(a, b)):
            if x != y:
                _report(x, y, f"{path}[{index}]", shown)
        return
    shown.append(path)
    print(f"    {path}: {str(a)[:70]} -> {str(b)[:70]}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
