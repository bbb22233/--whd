from __future__ import annotations

import json
import sys
from dataclasses import replace
from typing import Any

from backend_py.data_io import read_json, write_csv, write_json
from backend_py.reports_reader import DATA_CLEAN_DIR, DATA_RAW_DIR
from backend_py.research.clean import candles_to_csv_rows, clean_okx_raw
from backend_py.research.config import ResearchConfig, file_stem, parse_args
from backend_py.research.okx import download_okx_history


def split_csv_values(values: list[str]) -> list[str]:
    return [item.strip() for value in values for item in str(value).split(",") if item.strip()]


def collect_option_values(argv: list[str], start_index: int) -> list[str]:
    values = []
    for index in range(start_index, len(argv)):
        value = argv[index]
        if str(value).startswith("--"):
            break
        values.append(value)
    return values


def normalize_bar(value: str) -> str:
    bar = str(value).strip()
    return "1D" if bar == "1" else bar


def parse_batch_args(argv: list[str]) -> dict[str, Any]:
    config = parse_args(argv)
    if "--instrument" not in argv:
        config.instrument = "BTC-USDT"
    symbols = [config.instrument]
    bars = [config.bar]
    download = True
    clean = True
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--symbols":
            values = collect_option_values(argv, index + 1)
            symbols = split_csv_values(values)
            index += len(values) + 1
        elif arg == "--bars":
            values = collect_option_values(argv, index + 1)
            bars = [normalize_bar(item) for item in split_csv_values(values)]
            index += len(values) + 1
        elif arg == "--download-only":
            clean = False
            index += 1
        elif arg == "--clean-only":
            download = False
            index += 1
        else:
            index += 1
    return {"config": config, "symbols": list(dict.fromkeys(symbols)), "bars": list(dict.fromkeys(bars)), "download": download, "clean": clean}


def run_one(config: ResearchConfig, *, download: bool, clean: bool) -> dict[str, Any]:
    stem = file_stem(config)
    raw_path = DATA_RAW_DIR / f"{stem}_raw.json"
    clean_json_path = DATA_CLEAN_DIR / f"{stem}_clean.json"
    clean_csv_path = DATA_CLEAN_DIR / f"{stem}_clean.csv"
    result: dict[str, Any] = {"instrument": config.instrument, "bar": config.bar, "rawPath": str(raw_path)}

    if download:
        raw_payload = download_okx_history(config)
        write_json(raw_path, raw_payload)
        result.update({"download": "ok", "rawRows": raw_payload["rowCount"], "pageCount": raw_payload["pageCount"]})
    else:
        raw_payload = read_json(raw_path)
        result["download"] = "skipped"

    if clean:
        clean_payload = clean_okx_raw(raw_payload)
        write_json(clean_json_path, clean_payload)
        write_csv(clean_csv_path, candles_to_csv_rows(clean_payload["candles"]))
        result.update({"clean": "ok", "cleanRows": clean_payload["metadata"]["cleanRows"], "cleanJsonPath": str(clean_json_path), "cleanCsvPath": str(clean_csv_path)})
    else:
        result["clean"] = "skipped"

    return result


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    parsed = parse_batch_args(args)
    config: ResearchConfig = parsed["config"]
    steps = []
    errors = []
    for bar in parsed["bars"]:
        for symbol in parsed["symbols"]:
            try:
                scoped_config = replace(config, instrument=symbol, bar=bar)
                steps.append(run_one(scoped_config, download=parsed["download"], clean=parsed["clean"]))
            except Exception as error:  # noqa: BLE001 - batch runner reports per-scope failures.
                failure = {"instrument": symbol, "bar": bar, "status": "failed", "message": str(error)}
                steps.append(failure)
                errors.append(failure)

    print(
        json.dumps(
            {
                "step": "python-data-pipeline",
                "symbols": parsed["symbols"],
                "bars": parsed["bars"],
                "stepCount": len(steps),
                "successCount": len(steps) - len(errors),
                "errorCount": len(errors),
                "steps": steps,
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
