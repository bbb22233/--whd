from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from backend_py.reports_reader import REPORTS_DIR
from backend_py.research.config import parse_args, report_stem


VALUE_TOLERANCE = 1e-3
METADATA_KEYS = ["instrument", "bar", "fromDate", "toDate", "firstDate", "lastDate", "snapshotCount", "observationRows", "horizons"]
PAYLOAD_KEYS = ["strategyScores", "currentComponentRows", "componentSummaryRows"]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def close_enough(left: Any, right: Any, tolerance: float = VALUE_TOLERANCE) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= tolerance
    return left == right


def compare_value(path: str, left: Any, right: Any, failures: list[str]) -> None:
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
        compare_value(f"{path}.{key}", left_value, right[key], failures)


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    config = parse_args(args)
    stem = report_stem(config)
    node_path = REPORTS_DIR / f"{stem}_market_weather_router.json"
    python_path = REPORTS_DIR / f"{stem}_market_weather_router_py.json"
    node_payload = load_json(node_path)
    python_payload = load_json(python_path)
    failures: list[str] = []

    for key in METADATA_KEYS:
        compare_value(f"metadata.{key}", node_payload.get("metadata", {}).get(key), python_payload.get("metadata", {}).get(key), failures)
    for key in PAYLOAD_KEYS:
        compare_value(key, node_payload.get(key), python_payload.get(key), failures)

    if failures:
        print(json.dumps({"status": "failed", "failureCount": len(failures), "failures": failures[:80]}, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    print(
        json.dumps(
            {
                "status": "ok",
                "nodePath": str(node_path),
                "pythonPath": str(python_path),
                "snapshotCount": python_payload["metadata"]["snapshotCount"],
                "strategyScoreCount": len(python_payload["strategyScores"]),
                "currentComponentRowCount": len(python_payload["currentComponentRows"]),
                "componentSummaryRowCount": len(python_payload["componentSummaryRows"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

