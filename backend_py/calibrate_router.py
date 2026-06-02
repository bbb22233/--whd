from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from backend_py.data_io import read_json, write_csv, write_json
from backend_py.reports_reader import DATA_CLEAN_DIR, REPORTS_DIR
from backend_py.research.config import file_stem, parse_args, report_stem
from backend_py.research.feature_factory import build_indicator_snapshots
from backend_py.research.market_weather_router import run_router_calibration


def official_enabled(args: list[str]) -> bool:
    return "--official" in args


def plan_outputs_enabled(args: list[str]) -> bool:
    return "--plan-outputs" in args


def output_suffix(official: bool) -> str:
    return "" if official else "_py"


def output_plan(paths: list[Path], *, official: bool, suffix: str) -> dict[str, Any]:
    return {
        "step": "calibrate-router-output-plan",
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
    calibration_json_path = REPORTS_DIR / f"{report_name}_router_calibration{suffix}.json"
    calibration_csv_path = REPORTS_DIR / f"{report_name}_router_calibration{suffix}.csv"
    current_csv_path = REPORTS_DIR / f"{report_name}_router_current_signals{suffix}.csv"

    if plan_outputs_enabled(args):
        print(json.dumps(output_plan([calibration_json_path, calibration_csv_path, current_csv_path], official=official, suffix=suffix), ensure_ascii=False, indent=2))
        return

    clean_payload = read_json(input_path)
    snapshots = build_indicator_snapshots(clean_payload["candles"], config)
    result = run_router_calibration(clean_payload, config, snapshots)

    write_json(calibration_json_path, {"metadata": result["metadata"], "calibrationRows": result["calibrationRows"]})
    write_csv(calibration_csv_path, result["calibrationRows"])
    write_csv(current_csv_path, result["metadata"]["currentSignals"])

    print(
        json.dumps(
            {
                "step": "calibrate-router-py",
                "official": official,
                "suffix": suffix,
                "inputPath": str(input_path),
                "calibrationJsonPath": str(calibration_json_path),
                "calibrationCsvPath": str(calibration_csv_path),
                "currentCsvPath": str(current_csv_path),
                "metadata": result["metadata"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
