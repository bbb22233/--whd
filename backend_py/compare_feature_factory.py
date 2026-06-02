from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from backend_py.reports_reader import REPORTS_DIR
from backend_py.research.config import parse_args, report_stem


VALUE_TOLERANCE = 1e-3


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def close_enough(left: Any, right: Any, tolerance: float = VALUE_TOLERANCE) -> bool:
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return abs(float(left) - float(right)) <= tolerance
    return left == right


def compare_mapping(path: str, left: dict[str, Any], right: dict[str, Any], failures: list[str]) -> None:
    for key, left_value in left.items():
        if key not in right:
            failures.append(f"{path}.{key}: missing in python payload")
            continue
        right_value = right[key]
        if isinstance(left_value, dict) and isinstance(right_value, dict):
            compare_mapping(f"{path}.{key}", left_value, right_value, failures)
        elif not close_enough(left_value, right_value):
            failures.append(f"{path}.{key}: node={left_value!r} python={right_value!r}")


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    config = parse_args(args)
    stem = report_stem(config)
    node_path = REPORTS_DIR / f"{stem}_feature_factory.json"
    python_path = REPORTS_DIR / f"{stem}_feature_factory_py.json"
    node_payload = load_json(node_path)
    python_payload = load_json(python_path)
    failures: list[str] = []

    for key in ["instrument", "bar", "fromDate", "toDate", "firstDate", "lastDate", "snapshotCount", "featureCount"]:
        if node_payload["metadata"].get(key) != python_payload["metadata"].get(key):
            failures.append(f"metadata.{key}: node={node_payload['metadata'].get(key)!r} python={python_payload['metadata'].get(key)!r}")

    if node_payload["features"] != python_payload["features"]:
        failures.append("features: feature definitions differ")

    compare_mapping("featureStats", node_payload["featureStats"], python_payload["featureStats"], failures)

    node_current = node_payload.get("current") or {}
    python_current = python_payload.get("current") or {}
    for key in ["date", "close"]:
        if not close_enough(node_current.get(key), python_current.get(key)):
            failures.append(f"current.{key}: node={node_current.get(key)!r} python={python_current.get(key)!r}")
    compare_mapping("current.values", node_current.get("values") or {}, python_current.get("values") or {}, failures)

    if failures:
        print(json.dumps({"status": "failed", "failureCount": len(failures), "failures": failures[:50]}, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    print(
        json.dumps(
            {
                "status": "ok",
                "nodePath": str(node_path),
                "pythonPath": str(python_path),
                "snapshotCount": python_payload["metadata"]["snapshotCount"],
                "featureCount": python_payload["metadata"]["featureCount"],
                "currentDate": python_current.get("date"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

