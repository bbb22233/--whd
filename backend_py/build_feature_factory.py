from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
from typing import Any

from backend_py.reports_reader import DATA_CLEAN_DIR, PROJECT_ROOT, REPORTS_DIR
from backend_py.research.config import file_stem, parse_args, report_stem
from backend_py.research.feature_factory import build_feature_factory_core


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\ufeff", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def official_enabled(args: list[str]) -> bool:
    return "--official" in args


def plan_outputs_enabled(args: list[str]) -> bool:
    return "--plan-outputs" in args


def output_suffix(official: bool) -> str:
    return "" if official else "_py"


def output_plan(paths: list[Path], *, official: bool, suffix: str) -> dict[str, Any]:
    return {
        "step": "build-feature-factory-output-plan",
        "official": official,
        "suffix": suffix,
        "pathCount": len(paths),
        "existingCount": sum(1 for path in paths if path.exists()),
        "missingCount": sum(1 for path in paths if not path.exists()),
        "paths": [{"path": str(path), "exists": path.exists()} for path in paths],
    }


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    config = parse_args(args)
    stem = file_stem(config)
    report_name = report_stem(config)
    input_path = DATA_CLEAN_DIR / f"{stem}_clean.json"
    output_dir = REPORTS_DIR
    official = official_enabled(args)
    suffix = output_suffix(official)
    feature_json_path = output_dir / f"{report_name}_feature_factory{suffix}.json"
    feature_csv_path = output_dir / f"{report_name}_feature_factory_rows{suffix}.csv"

    if plan_outputs_enabled(args):
        print(json.dumps(output_plan([feature_json_path, feature_csv_path], official=official, suffix=suffix), ensure_ascii=False, indent=2))
        return

    clean_payload = json.loads(input_path.read_text(encoding="utf-8"))
    result = build_feature_factory_core(clean_payload, config)

    write_json(
        feature_json_path,
        {
            "metadata": result["metadata"],
            "features": result["features"],
            "featureStats": result["featureStats"],
            "current": result["current"],
        },
    )
    write_csv(feature_csv_path, result["featureRows"])

    print(
        json.dumps(
            {
                "step": "build-feature-factory-py",
                "official": official,
                "suffix": suffix,
                "inputPath": str(input_path),
                "featureJsonPath": str(feature_json_path),
                "featureCsvPath": str(feature_csv_path),
                "metadata": result["metadata"],
                "current": result["current"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
