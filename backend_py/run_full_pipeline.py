from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import sys
from typing import Any

from backend_py.build_summary import DEFAULT_SYMBOLS
from backend_py.data_io import read_json, write_csv, write_json
from backend_py.reports_reader import DATA_CLEAN_DIR, DATA_RAW_DIR, REPORTS_DIR
from backend_py.research.clean import candles_to_csv_rows, clean_okx_raw, derive_clean_payload
from backend_py.research.config import ResearchConfig, file_stem, parse_args, report_stem
from backend_py.research.deviation_rules import build_deviation_rules_from_clean
from backend_py.research.feature_factory import build_feature_factory_core
from backend_py.research.market_weather_router import build_market_weather_router_components
from backend_py.research.okx import download_okx_history
from backend_py.research.summary import build_summary_row, quality_summary


DERIVED_BARS = {"8H": {"sourceBar": "4H", "groupSize": 2}}


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
    official = False
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
        elif arg == "--official":
            official = True
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
        "official": official,
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_suffix(official: bool) -> str:
    return "" if official else "_py_full"


def report_path(report_name: str, suffix: str, kind: str, extension: str = "json") -> Any:
    return REPORTS_DIR / f"{report_name}_{kind}{suffix}.{extension}"


def summary_path(stem: str, suffix: str, extension: str = "json") -> Any:
    return REPORTS_DIR / f"{stem}{suffix}.{extension}"


def create_symbol_config(base_config: ResearchConfig, instrument: str) -> ResearchConfig:
    return replace(base_config, instrument=instrument)


def create_bar_config(base_config: ResearchConfig, bar: str) -> ResearchConfig:
    return replace(base_config, bar=bar)


def read_json_if_exists(path: Any) -> dict[str, Any] | None:
    try:
        return read_json(path)
    except FileNotFoundError:
        return None


def write_feature_report(report_name: str, suffix: str, result: dict[str, Any]) -> dict[str, str]:
    feature_json_path = report_path(report_name, suffix, "feature_factory")
    feature_csv_path = report_path(report_name, suffix, "feature_factory_rows", "csv")
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
    return {"featureJsonPath": str(feature_json_path), "featureCsvPath": str(feature_csv_path)}


def write_deviation_report(report_name: str, suffix: str, rules: dict[str, Any]) -> dict[str, str]:
    output_json_path = report_path(report_name, suffix, "deviation_rules")
    current_csv_path = report_path(report_name, suffix, "deviation_rules_current", "csv")
    library_csv_path = report_path(report_name, suffix, "deviation_rule_library", "csv")
    write_json(output_json_path, rules)
    write_csv(current_csv_path, rules["currentRuleRows"])
    write_csv(library_csv_path, rules["ruleLibraryRows"])
    return {"deviationJsonPath": str(output_json_path), "deviationCurrentCsvPath": str(current_csv_path), "deviationLibraryCsvPath": str(library_csv_path)}


def write_router_report(report_name: str, suffix: str, result: dict[str, Any]) -> dict[str, str]:
    output_json_path = report_path(report_name, suffix, "market_weather_router")
    current_csv_path = report_path(report_name, suffix, "market_weather_current", "csv")
    scores_csv_path = report_path(report_name, suffix, "market_weather_scores", "csv")
    components_csv_path = report_path(report_name, suffix, "market_weather_components_current", "csv")
    summary_csv_path = report_path(report_name, suffix, "market_weather_component_summary", "csv")
    write_json(
        output_json_path,
        {
            "metadata": result["metadata"],
            "current": result["current"],
            "strategyScores": result["strategyScores"],
            "deviationFinalWeather": result["deviationFinalWeather"],
            "currentComponentRows": result["currentComponentRows"],
            "componentSummaryRows": result["componentSummaryRows"],
        },
    )
    write_csv(current_csv_path, [result["current"]] if result.get("current") else [])
    write_csv(scores_csv_path, result["strategyScores"])
    write_csv(components_csv_path, result["currentComponentRows"])
    write_csv(summary_csv_path, result["componentSummaryRows"])
    return {"weatherJsonPath": str(output_json_path), "weatherCurrentCsvPath": str(current_csv_path), "weatherScoresCsvPath": str(scores_csv_path)}


def build_clean_payload(config: ResearchConfig, *, skip_download: bool, prefer_existing_source_raw: bool) -> tuple[dict[str, Any], dict[str, str]]:
    recipe = DERIVED_BARS.get(config.bar)
    source_config = replace(config, bar=recipe["sourceBar"]) if recipe else config
    stem = file_stem(config)
    source_stem = file_stem(source_config)
    raw_path = DATA_RAW_DIR / f"{source_stem}_raw.json"
    clean_json_path = DATA_CLEAN_DIR / f"{stem}_clean.json"
    clean_csv_path = DATA_CLEAN_DIR / f"{stem}_clean.csv"

    existing_source_raw = read_json_if_exists(raw_path) if recipe and prefer_existing_source_raw else None
    if skip_download:
        raw_payload = read_json(raw_path)
    else:
        raw_payload = existing_source_raw or download_okx_history(source_config)
    write_json(raw_path, raw_payload)

    source_clean_payload = clean_okx_raw(raw_payload)
    clean_payload = (
        derive_clean_payload(source_clean_payload, instrument=config.instrument, target_bar=config.bar, requested_days=config.days, source_bar=recipe["sourceBar"], group_size=recipe["groupSize"])
        if recipe
        else source_clean_payload
    )
    write_json(clean_json_path, clean_payload)
    write_csv(clean_csv_path, candles_to_csv_rows(clean_payload["candles"]))
    return clean_payload, {"rawPath": str(raw_path), "cleanJsonPath": str(clean_json_path), "cleanCsvPath": str(clean_csv_path)}


def run_one_symbol_from_reports(base_config: ResearchConfig, instrument: str, suffix: str) -> dict[str, Any]:
    config = create_symbol_config(base_config, instrument)
    stem = file_stem(config)
    report_name = report_stem(config)
    clean_payload = read_json(DATA_CLEAN_DIR / f"{stem}_clean.json")
    weather_result = read_json(report_path(report_name, "", "market_weather_router"))
    feature_result = read_json_if_exists(report_path(report_name, "", "feature_factory"))
    deviation_rules = read_json_if_exists(report_path(report_name, "", "deviation_rules"))
    return {
        "summaryRow": build_summary_row(config=config, clean_payload=clean_payload, feature_result=feature_result, weather_result=weather_result, deviation_rules=deviation_rules or {"finalWeather": weather_result.get("deviationFinalWeather")}),
        "outputs": {"cleanJsonPath": str(DATA_CLEAN_DIR / f"{stem}_clean.json")},
    }


def run_one_symbol(base_config: ResearchConfig, instrument: str, options: dict[str, Any]) -> dict[str, Any]:
    config = create_symbol_config(base_config, instrument)
    suffix = output_suffix(options["official"])
    if options["fromReports"]:
        return run_one_symbol_from_reports(base_config, instrument, suffix)

    clean_payload, outputs = build_clean_payload(config, skip_download=options["skipDownload"], prefer_existing_source_raw=options["preferExistingSourceRaw"])
    report_name = report_stem(config)
    feature_result = None
    deviation_rules = None

    if not options["summaryOnly"]:
        feature_result = build_feature_factory_core(clean_payload, config)
        outputs.update(write_feature_report(report_name, suffix, feature_result))
        deviation_rules = build_deviation_rules_from_clean(clean_payload, config)
        outputs.update(write_deviation_report(report_name, suffix, deviation_rules))

    weather_result = build_market_weather_router_components(clean_payload, config)
    outputs.update(write_router_report(report_name, suffix, weather_result))
    return {
        "summaryRow": build_summary_row(config=config, clean_payload=clean_payload, feature_result=feature_result, weather_result=weather_result, deviation_rules=deviation_rules or {"finalWeather": weather_result.get("deviationFinalWeather")}),
        "outputs": outputs,
    }


def write_bar_summary(*, config: ResearchConfig, suffix: str, symbols: list[str], rows: list[dict[str, Any]], errors: list[dict[str, Any]], skip_download: bool, summary_only: bool, from_reports: bool, started_at: datetime) -> dict[str, Any]:
    output_stem = f"multi_{config.bar}_market_weather_current"
    summary_json_path = summary_path(output_stem, suffix)
    summary_csv_path = summary_path(output_stem, suffix, "csv")
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
                "finishedAt": utc_now_iso(),
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
    return {"bar": config.bar, "summaryJsonPath": str(summary_json_path), "summaryCsvPath": str(summary_csv_path), "successCount": len(rows), "weatherCount": quality["weatherCount"], "weightedWeatherCount": quality["weightedWeatherCount"], "averagePeriodWeight": quality["averagePeriodWeight"], "lowWeightCount": quality["lowWeightCount"], "insufficientHistoryCount": quality["insufficientHistoryCount"], "errorCount": len(errors)}


def write_combined_summary(*, suffix: str, bars: list[str], symbols: list[str], rows: list[dict[str, Any]], errors: list[dict[str, Any]], skip_download: bool, summary_only: bool, from_reports: bool, started_at: datetime) -> dict[str, Any]:
    summary_json_path = summary_path("multi_period_market_weather_current", suffix)
    summary_csv_path = summary_path("multi_period_market_weather_current", suffix, "csv")
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
                "finishedAt": utc_now_iso(),
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
    return {"summaryJsonPath": str(summary_json_path), "summaryCsvPath": str(summary_csv_path), "successCount": len(rows), "weatherCount": quality["weatherCount"], "weightedWeatherCount": quality["weightedWeatherCount"], "averagePeriodWeight": quality["averagePeriodWeight"], "lowWeightCount": quality["lowWeightCount"], "insufficientHistoryCount": quality["insufficientHistoryCount"], "errorCount": len(errors)}


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    parsed = parse_batch_args(args)
    config: ResearchConfig = parsed["config"]
    symbols: list[str] = parsed["symbols"]
    bars: list[str] = parsed["bars"]
    suffix = output_suffix(parsed["official"])
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
                result = run_one_symbol(
                    bar_config,
                    symbol,
                    {
                        "skipDownload": parsed["skipDownload"],
                        "summaryOnly": parsed["summaryOnly"],
                        "fromReports": parsed["fromReports"],
                        "official": parsed["official"],
                        "preferExistingSourceRaw": "4H" in bars and bar == "8H",
                    },
                )
                rows.append(result["summaryRow"])
            except Exception as error:  # noqa: BLE001 - mirrors Node batch error capture.
                errors.append({"instrument": symbol, "bar": bar_config.bar, "message": str(error)})

        bar_summaries.append(write_bar_summary(config=bar_config, suffix=suffix, symbols=symbols, rows=rows, errors=errors, skip_download=parsed["skipDownload"], summary_only=parsed["summaryOnly"], from_reports=parsed["fromReports"], started_at=bar_started_at))
        all_rows.extend(rows)
        all_errors.extend(errors)

    combined = write_combined_summary(suffix=suffix, bars=bars, symbols=symbols, rows=all_rows, errors=all_errors, skip_download=parsed["skipDownload"], summary_only=parsed["summaryOnly"], from_reports=parsed["fromReports"], started_at=started_at)
    print(json.dumps({"step": "multi-symbol-weather-summary-py-full", "official": parsed["official"], "suffix": suffix, **combined, "barSummaries": bar_summaries, "errors": all_errors}, ensure_ascii=False, indent=2))
    if not all_rows or all_errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
