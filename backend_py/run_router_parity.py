from __future__ import annotations

import json
import sys
from dataclasses import replace
from typing import Any

from backend_py.build_market_weather_router import main as build_market_weather_router
from backend_py.compare_market_weather_router import main as compare_market_weather_router
from backend_py.research.config import ResearchConfig, parse_args


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
    if "--days" not in argv:
        config.days = 3650
    symbols = [config.instrument]
    bars = [config.bar]
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
        else:
            index += 1

    return {
        "config": config,
        "symbols": list(dict.fromkeys(symbols)),
        "bars": list(dict.fromkeys(bars)),
    }


def scoped_args(config: ResearchConfig, instrument: str, bar: str) -> list[str]:
    args = ["--instrument", instrument, "--bar", bar, "--days", str(config.days)]
    if config.fromDate:
        args.extend(["--from", config.fromDate])
    if config.toDate:
        args.extend(["--to", config.toDate])
    return args


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    parsed = parse_batch_args(args)
    config: ResearchConfig = parsed["config"]
    symbols: list[str] = parsed["symbols"]
    bars: list[str] = parsed["bars"]
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for bar in bars:
        for symbol in symbols:
            task_args = scoped_args(replace(config, instrument=symbol, bar=bar), symbol, bar)
            try:
                build_market_weather_router(task_args)
                compare_market_weather_router(task_args)
                results.append({"instrument": symbol, "bar": bar, "status": "ok"})
            except SystemExit as error:
                if error.code == 0:
                    results.append({"instrument": symbol, "bar": bar, "status": "ok"})
                else:
                    errors.append({"instrument": symbol, "bar": bar, "message": f"exited with {error.code}"})
            except Exception as error:  # noqa: BLE001 - batch parity should report all scoped failures.
                errors.append({"instrument": symbol, "bar": bar, "message": str(error)})

    print(
        json.dumps(
            {
                "step": "python-router-parity",
                "symbols": symbols,
                "bars": bars,
                "successCount": len(results),
                "errorCount": len(errors),
                "results": results,
                "errors": errors,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not results or errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
