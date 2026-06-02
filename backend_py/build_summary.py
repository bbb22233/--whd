from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

from backend_py.reports_reader import DATA_CLEAN_DIR, REPORTS_DIR
from backend_py.research.config import ResearchConfig, file_stem, parse_args, report_stem
from backend_py.research.summary import build_summary_row, quality_summary


DEFAULT_SYMBOLS = [
    "BTC-USDT",
    "ETH-USDT",
    "SOL-USDT",
    "BNB-USDT",
    "XRP-USDT",
    "DOGE-USDT",
    "ADA-USDT",
    "LINK-USDT",
    "AVAX-USDT",
    "TON-USDT",
    "TRX-USDT",
    "DOT-USDT",
    "BCH-USDT",
    "LTC-USDT",
    "UNI-USDT",
    "AAVE-USDT",
    "NEAR-USDT",
    "OP-USDT",
    "ARB-USDT",
    "SUI-USDT",
    "APT-USDT",
    "FIL-USDT",
    "ETC-USDT",
    "ATOM-USDT",
    "INJ-USDT",
    "STX-USDT",
    "IMX-USDT",
    "WLD-USDT",
    "AR-USDT",
    "XLM-USDT",
    "ICP-USDT",
    "HBAR-USDT",
    "ALGO-USDT",
    "LDO-USDT",
    "CRV-USDT",
    "ENS-USDT",
    "PENDLE-USDT",
    "JUP-USDT",
    "PYTH-USDT",
    "TIA-USDT",
    "ONDO-USDT",
    "FET-USDT",
    "PEPE-USDT",
    "SHIB-USDT",
    "BONK-USDT",
    "FLOKI-USDT",
    "WIF-USDT",
    "ORDI-USDT",
    "SATS-USDT",
    "NOT-USDT",
    "ENA-USDT",
    "W-USDT",
    "STRK-USDT",
    "ZK-USDT",
    "ZRO-USDT",
    "GALA-USDT",
    "SAND-USDT",
    "MANA-USDT",
]


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
    symbols = DEFAULT_SYMBOLS
    bars = [config.bar]
    skip_download = False
    summary_only = False
    from_reports = False
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
        elif arg == "--skip-download":
            skip_download = True
            index += 1
        elif arg == "--summary-only":
            summary_only = True
            index += 1
        elif arg == "--from-reports":
            from_reports = True
            index += 1
        else:
            index += 1

    return {
        "config": config,
        "symbols": list(dict.fromkeys(symbols)),
        "bars": list(dict.fromkeys(bars)),
        "skipDownload": skip_download,
        "summaryOnly": summary_only,
        "fromReports": from_reports,
    }


def create_symbol_config(base_config: ResearchConfig, instrument: str) -> ResearchConfig:
    config = parse_args([])
    config.instrument = instrument
    config.bar = base_config.bar
    config.days = base_config.days
    config.requestLimit = base_config.requestLimit
    config.fromDate = base_config.fromDate
    config.toDate = base_config.toDate
    config.indicator = base_config.indicator
    config.thresholds = base_config.thresholds
    config.horizons = base_config.horizons
    return config


def create_bar_config(base_config: ResearchConfig, bar: str) -> ResearchConfig:
    config = create_symbol_config(base_config, base_config.instrument)
    config.bar = bar
    return config


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return read_json(path)


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


def run_one_symbol_from_reports(base_config: ResearchConfig, instrument: str) -> dict[str, Any]:
    config = create_symbol_config(base_config, instrument)
    stem = file_stem(config)
    report_name = report_stem(config)
    clean_payload = read_json(DATA_CLEAN_DIR / f"{stem}_clean.json")
    weather_result = read_json(REPORTS_DIR / f"{report_name}_market_weather_router.json")
    feature_result = read_json_if_exists(REPORTS_DIR / f"{report_name}_feature_factory.json")
    deviation_rules = read_json_if_exists(REPORTS_DIR / f"{report_name}_deviation_rules.json")

    return build_summary_row(
        config=config,
        clean_payload=clean_payload,
        feature_result=feature_result,
        weather_result=weather_result,
        deviation_rules=deviation_rules or {"finalWeather": weather_result.get("deviationFinalWeather")},
    )


def write_bar_summary(
    *,
    config: ResearchConfig,
    symbols: list[str],
    rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    skip_download: bool,
    summary_only: bool,
    from_reports: bool,
    started_at: datetime,
) -> dict[str, Any]:
    output_stem = f"multi_{config.bar}_market_weather_current_py"
    summary_json_path = REPORTS_DIR / f"{output_stem}.json"
    summary_csv_path = REPORTS_DIR / f"{output_stem}.csv"
    quality = quality_summary(rows)
    write_json(
        summary_json_path,
        {
            "metadata": {
                "symbols": symbols,
                "bar": config.bar,
                "days": config.days,
                "skipDownload": skip_download,
                "summaryOnly": summary_only,
                "fromReports": from_reports,
                "startedAt": started_at.isoformat().replace("+00:00", "Z"),
                "finishedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "successCount": len(rows),
                "weatherCount": quality["weatherCount"],
                "weightedWeatherCount": quality["weightedWeatherCount"],
                "averagePeriodWeight": quality["averagePeriodWeight"],
                "lowWeightCount": quality["lowWeightCount"],
                "insufficientHistoryCount": quality["insufficientHistoryCount"],
                "errorCount": len(errors),
            },
            "rows": rows,
            "errors": errors,
        },
    )
    write_csv(summary_csv_path, rows)
    return {
        "bar": config.bar,
        "summaryJsonPath": str(summary_json_path),
        "summaryCsvPath": str(summary_csv_path),
        "successCount": len(rows),
        "weatherCount": quality["weatherCount"],
        "weightedWeatherCount": quality["weightedWeatherCount"],
        "averagePeriodWeight": quality["averagePeriodWeight"],
        "lowWeightCount": quality["lowWeightCount"],
        "insufficientHistoryCount": quality["insufficientHistoryCount"],
        "errorCount": len(errors),
    }


def write_combined_summary(
    *,
    bars: list[str],
    symbols: list[str],
    rows: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    skip_download: bool,
    summary_only: bool,
    from_reports: bool,
    started_at: datetime,
) -> dict[str, Any]:
    summary_json_path = REPORTS_DIR / "multi_period_market_weather_current_py.json"
    summary_csv_path = REPORTS_DIR / "multi_period_market_weather_current_py.csv"
    quality = quality_summary(rows)
    write_json(
        summary_json_path,
        {
            "metadata": {
                "symbols": symbols,
                "bars": bars,
                "skipDownload": skip_download,
                "summaryOnly": summary_only,
                "fromReports": from_reports,
                "startedAt": started_at.isoformat().replace("+00:00", "Z"),
                "finishedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "successCount": len(rows),
                "weatherCount": quality["weatherCount"],
                "weightedWeatherCount": quality["weightedWeatherCount"],
                "averagePeriodWeight": quality["averagePeriodWeight"],
                "lowWeightCount": quality["lowWeightCount"],
                "insufficientHistoryCount": quality["insufficientHistoryCount"],
                "errorCount": len(errors),
            },
            "rows": rows,
            "errors": errors,
        },
    )
    write_csv(summary_csv_path, rows)
    return {
        "summaryJsonPath": str(summary_json_path),
        "summaryCsvPath": str(summary_csv_path),
        "successCount": len(rows),
        "weatherCount": quality["weatherCount"],
        "weightedWeatherCount": quality["weightedWeatherCount"],
        "averagePeriodWeight": quality["averagePeriodWeight"],
        "lowWeightCount": quality["lowWeightCount"],
        "insufficientHistoryCount": quality["insufficientHistoryCount"],
        "errorCount": len(errors),
    }


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    parsed = parse_batch_args(args)
    config: ResearchConfig = parsed["config"]
    symbols: list[str] = parsed["symbols"]
    bars: list[str] = parsed["bars"]
    started_at = datetime.now(timezone.utc)
    all_rows: list[dict[str, Any]] = []
    all_errors: list[dict[str, Any]] = []
    bar_summaries = []

    for bar in bars:
        bar_started_at = datetime.now(timezone.utc)
        bar_config = create_bar_config(config, bar)
        rows: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for symbol in symbols:
            try:
                rows.append(run_one_symbol_from_reports(bar_config, symbol))
            except Exception as error:  # noqa: BLE001 - mirrors Node batch error capture.
                errors.append({"instrument": symbol, "bar": bar_config.bar, "message": str(error)})

        bar_summaries.append(
            write_bar_summary(
                config=bar_config,
                symbols=symbols,
                rows=rows,
                errors=errors,
                skip_download=parsed["skipDownload"],
                summary_only=parsed["summaryOnly"],
                from_reports=parsed["fromReports"],
                started_at=bar_started_at,
            )
        )
        all_rows.extend(rows)
        all_errors.extend(errors)

    combined = write_combined_summary(
        bars=bars,
        symbols=symbols,
        rows=all_rows,
        errors=all_errors,
        skip_download=parsed["skipDownload"],
        summary_only=parsed["summaryOnly"],
        from_reports=parsed["fromReports"],
        started_at=started_at,
    )
    print(json.dumps({"step": "multi-symbol-weather-summary-py", **combined, "barSummaries": bar_summaries, "errors": all_errors}, ensure_ascii=False, indent=2))
    if not all_rows or all_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
