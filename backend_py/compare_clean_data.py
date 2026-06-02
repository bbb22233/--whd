from __future__ import annotations

import json
import sys
from typing import Any

from backend_py.data_io import read_json
from backend_py.reports_reader import DATA_CLEAN_DIR, DATA_RAW_DIR
from backend_py.research.clean import clean_okx_raw
from backend_py.research.config import file_stem, parse_args


IGNORE_PATHS = {"metadata.cleanedAt"}
VALUE_TOLERANCE = 1e-9


def close_enough(left: Any, right: Any) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= VALUE_TOLERANCE
    return left == right


def compare_value(path: str, left: Any, right: Any, failures: list[str]) -> None:
    if path in IGNORE_PATHS:
        return
    if isinstance(left, dict) and isinstance(right, dict):
        compare_mapping(path, left, right, failures)
    elif isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            failures.append(f"{path}: length node={len(left)} python={len(right)}")
            return
        for index, (left_item, right_item) in enumerate(zip(left, right, strict=True)):
            compare_value(f"{path}[{index}]", left_item, right_item, failures)
    elif not close_enough(left, right):
        failures.append(f"{path}: node={left!r} python={right!r}")


def compare_mapping(path: str, left: dict[str, Any], right: dict[str, Any], failures: list[str]) -> None:
    left_keys = set(left.keys())
    right_keys = set(right.keys())
    if left_keys != right_keys:
        failures.append(f"{path}: key mismatch node_only={sorted(left_keys - right_keys)} python_only={sorted(right_keys - left_keys)}")
    for key, left_value in left.items():
        if key not in right:
            continue
        next_path = f"{path}.{key}" if path else key
        compare_value(next_path, left_value, right[key], failures)


def main(argv: list[str] | None = None) -> None:
    config = parse_args(list(argv if argv is not None else sys.argv[1:]))
    stem = file_stem(config)
    raw_path = DATA_RAW_DIR / f"{stem}_raw.json"
    node_path = DATA_CLEAN_DIR / f"{stem}_clean.json"
    raw_payload = read_json(raw_path)
    node_payload = read_json(node_path)
    python_payload = clean_okx_raw(raw_payload)
    failures: list[str] = []
    compare_value("", node_payload, python_payload, failures)
    if failures:
        print(json.dumps({"status": "failed", "failureCount": len(failures), "failures": failures[:80]}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    print(
        json.dumps(
            {
                "status": "ok",
                "nodePath": str(node_path),
                "rawPath": str(raw_path),
                "instrument": node_payload.get("metadata", {}).get("instrument"),
                "bar": node_payload.get("metadata", {}).get("bar"),
                "cleanRows": len(node_payload.get("candles") or []),
                "missingBars": len(node_payload.get("metadata", {}).get("missingBars") or []),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
