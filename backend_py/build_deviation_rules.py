from __future__ import annotations

import csv
import json
from pathlib import Path
import sys
from typing import Any

from backend_py.reports_reader import DATA_CLEAN_DIR, REPORTS_DIR
from backend_py.research.config import file_stem, parse_args, report_stem
from backend_py.research.deviation_rules import build_deviation_rules_from_clean


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
        "step": "build-deviation-rules-output-plan",
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
    official = official_enabled(args)
    suffix = output_suffix(official)
    output_json_path = REPORTS_DIR / f"{report_name}_deviation_rules{suffix}.json"
    current_csv_path = REPORTS_DIR / f"{report_name}_deviation_rules_current{suffix}.csv"
    library_csv_path = REPORTS_DIR / f"{report_name}_deviation_rule_library{suffix}.csv"

    if plan_outputs_enabled(args):
        print(json.dumps(output_plan([output_json_path, current_csv_path, library_csv_path], official=official, suffix=suffix), ensure_ascii=False, indent=2))
        return

    clean_payload = json.loads(input_path.read_text(encoding="utf-8"))
    rules = build_deviation_rules_from_clean(clean_payload, config)

    write_json(output_json_path, rules)
    write_csv(current_csv_path, rules["currentRuleRows"])
    write_csv(library_csv_path, rules["ruleLibraryRows"])
    print(
        json.dumps(
            {
                "step": "build-deviation-rules-py",
                "official": official,
                "suffix": suffix,
                "inputPath": str(input_path),
                "outputJsonPath": str(output_json_path),
                "currentCsvPath": str(current_csv_path),
                "libraryCsvPath": str(library_csv_path),
                "metadata": rules["metadata"],
                "finalWeather": rules["finalWeather"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
