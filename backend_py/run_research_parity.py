from __future__ import annotations

import contextlib
import io
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from backend_py.build_deviation_rules import main as build_deviation_rules
from backend_py.build_feature_factory import main as build_feature_factory
from backend_py.build_market_weather_router import main as build_market_weather_router
from backend_py.build_summary import main as build_summary
from backend_py.compare_deviation_rules import main as compare_deviation_rules
from backend_py.compare_feature_factory import main as compare_feature_factory
from backend_py.compare_market_weather_router import main as compare_market_weather_router
from backend_py.compare_summary import main as compare_summary
from backend_py.reports_reader import REPORTS_DIR
from backend_py.research.config import ResearchConfig, parse_args, report_stem


CliMain = Callable[[list[str] | None], None]


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
    return {"config": config, "symbols": list(dict.fromkeys(symbols)), "bars": list(dict.fromkeys(bars))}


def scoped_args(config: ResearchConfig, instrument: str, bar: str) -> list[str]:
    args = ["--instrument", instrument, "--bar", bar, "--days", str(config.days)]
    if config.fromDate:
        args.extend(["--from", config.fromDate])
    if config.toDate:
        args.extend(["--to", config.toDate])
    return args


def batch_scope_args(config: ResearchConfig, symbols: list[str], bars: list[str]) -> list[str]:
    args = ["--from-reports", "--summary-only", "--symbols", *symbols, "--bars", ",".join(bars), "--days", str(config.days)]
    if config.fromDate:
        args.extend(["--from", config.fromDate])
    if config.toDate:
        args.extend(["--to", config.toDate])
    return args


def tail_text(value: str, limit: int = 1200) -> str:
    if len(value) <= limit:
        return value
    return value[-limit:]


def run_cli(label: str, fn: CliMain, args: list[str]) -> dict[str, Any]:
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            fn(args)
        return {"step": label, "status": "ok", "stdoutTail": tail_text(stdout.getvalue())}
    except SystemExit as error:
        status = "ok" if error.code == 0 else "failed"
        return {"step": label, "status": status, "exitCode": error.code, "stdoutTail": tail_text(stdout.getvalue())}
    except Exception as error:  # noqa: BLE001 - parity batch should keep step context.
        return {"step": label, "status": "failed", "message": str(error), "stdoutTail": tail_text(stdout.getvalue())}


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def deviation_golden_is_current(config: ResearchConfig) -> tuple[bool, str]:
    stem = report_stem(config)
    deviation = load_json_if_exists(REPORTS_DIR / f"{stem}_deviation_rules.json")
    router = load_json_if_exists(REPORTS_DIR / f"{stem}_market_weather_router.json")
    deviation_last = (deviation or {}).get("metadata", {}).get("lastDate")
    router_last = (router or {}).get("metadata", {}).get("lastDate")
    if not deviation or not router:
        return False, "missing_official_golden"
    if deviation_last != router_last:
        return False, f"stale_official_golden deviationLastDate={deviation_last} routerLastDate={router_last}"
    return True, "official_golden_current"


def list_scope(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def summary_golden_matches_scope(symbols: list[str], bars: list[str]) -> tuple[bool, str]:
    combined = load_json_if_exists(REPORTS_DIR / "multi_period_market_weather_current.json")
    if not combined:
        return False, "missing_official_summary_golden"
    metadata = combined.get("metadata", {})
    official_symbols = list_scope(metadata.get("symbols"))
    official_bars = list_scope(metadata.get("bars"))
    if official_symbols != symbols:
        return False, f"scope_mismatch officialSymbols={len(official_symbols)} requestedSymbols={len(symbols)}"
    if official_bars != bars:
        return False, f"scope_mismatch officialBars={','.join(official_bars)} requestedBars={','.join(bars)}"
    return True, "official_summary_scope_current"


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    parsed = parse_batch_args(args)
    config: ResearchConfig = parsed["config"]
    symbols: list[str] = parsed["symbols"]
    bars: list[str] = parsed["bars"]
    steps: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for bar in bars:
        for symbol in symbols:
            scoped_config = replace(config, instrument=symbol, bar=bar)
            task_args = scoped_args(scoped_config, symbol, bar)
            for label, fn in [
                ("feature_build", build_feature_factory),
                ("feature_compare", compare_feature_factory),
                ("deviation_build", build_deviation_rules),
            ]:
                result = {"instrument": symbol, "bar": bar, **run_cli(label, fn, task_args)}
                steps.append(result)
                if result["status"] == "failed":
                    errors.append(result)

            current, reason = deviation_golden_is_current(scoped_config)
            if current:
                result = {"instrument": symbol, "bar": bar, **run_cli("deviation_compare", compare_deviation_rules, task_args)}
            else:
                result = {"instrument": symbol, "bar": bar, "step": "deviation_compare", "status": "skipped", "reason": reason}
            steps.append(result)
            if result["status"] == "failed":
                errors.append(result)

            for label, fn in [
                ("router_build", build_market_weather_router),
                ("router_compare", compare_market_weather_router),
            ]:
                result = {"instrument": symbol, "bar": bar, **run_cli(label, fn, task_args)}
                steps.append(result)
                if result["status"] == "failed":
                    errors.append(result)

    summary_args = batch_scope_args(config, symbols, bars)
    result = {"instrument": ",".join(symbols), "bar": ",".join(bars), **run_cli("summary_build", build_summary, summary_args)}
    steps.append(result)
    if result["status"] == "failed":
        errors.append(result)

    current, reason = summary_golden_matches_scope(symbols, bars)
    if current:
        result = {"instrument": ",".join(symbols), "bar": ",".join(bars), **run_cli("summary_compare", compare_summary, summary_args)}
    else:
        result = {"instrument": ",".join(symbols), "bar": ",".join(bars), "step": "summary_compare", "status": "skipped", "reason": reason}
    steps.append(result)
    if result["status"] == "failed":
        errors.append(result)

    skipped = [step for step in steps if step["status"] == "skipped"]
    print(
        json.dumps(
            {
                "step": "python-research-parity",
                "symbols": symbols,
                "bars": bars,
                "stepCount": len(steps),
                "successCount": len([step for step in steps if step["status"] == "ok"]),
                "skippedCount": len(skipped),
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
