from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from backend_py.reports_reader import REPORTS_DIR
from backend_py.build_summary import parse_batch_args


VALUE_TOLERANCE = 1e-3
BAR_METADATA_IGNORE_KEYS = {"startedAt", "finishedAt"}
COMBINED_METADATA_IGNORE_KEYS = {"startedAt", "finishedAt"}


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


def metadata_ignore_keys(path: str) -> set[str]:
    if path.endswith(".metadata"):
        if path.startswith("bar"):
            return BAR_METADATA_IGNORE_KEYS
        if path.startswith("combined"):
            return COMBINED_METADATA_IGNORE_KEYS
    return set()


def compare_mapping(path: str, left: dict[str, Any], right: dict[str, Any], failures: list[str]) -> None:
    ignore = metadata_ignore_keys(path)
    left_keys = set(left.keys()) - ignore
    right_keys = set(right.keys()) - ignore
    if left_keys != right_keys:
        failures.append(f"{path}: key mismatch node_only={sorted(left_keys - right_keys)} python_only={sorted(right_keys - left_keys)}")

    for key, left_value in left.items():
        if key in ignore:
            continue
        if key not in right:
            continue
        compare_value(f"{path}.{key}", left_value, right[key], failures)


def compare_file(label: str, node_path: Path, python_path: Path, failures: list[str]) -> None:
    if not node_path.exists():
        failures.append(f"{label}: missing node file {node_path}")
        return
    if not python_path.exists():
        failures.append(f"{label}: missing python file {python_path}")
        return
    compare_value(label, load_json(node_path), load_json(python_path), failures)


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    parsed = parse_batch_args(args)
    bars: list[str] = parsed["bars"]
    failures: list[str] = []

    for bar in bars:
        compare_file(
            f"bar[{bar}]",
            REPORTS_DIR / f"multi_{bar}_market_weather_current.json",
            REPORTS_DIR / f"multi_{bar}_market_weather_current_py.json",
            failures,
        )

    compare_file(
        "combined",
        REPORTS_DIR / "multi_period_market_weather_current.json",
        REPORTS_DIR / "multi_period_market_weather_current_py.json",
        failures,
    )

    if failures:
        print(json.dumps({"status": "failed", "failureCount": len(failures), "failures": failures[:80]}, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    combined = load_json(REPORTS_DIR / "multi_period_market_weather_current_py.json")
    print(
        json.dumps(
            {
                "status": "ok",
                "bars": bars,
                "rowCount": len(combined.get("rows") or []),
                "errorCount": len(combined.get("errors") or []),
                "weightedWeatherCount": combined.get("metadata", {}).get("weightedWeatherCount"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

