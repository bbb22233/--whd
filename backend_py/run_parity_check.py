from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from backend_py.compare_deviation_rules import main as compare_deviation_rules
from backend_py.compare_feature_factory import main as compare_feature_factory
from backend_py.compare_market_weather_router import main as compare_market_weather_router
from backend_py.compare_summary import main as compare_summary
from backend_py.reports_reader import PROJECT_ROOT, REPORTS_DIR
from backend_py.research.config import ResearchConfig, file_stem, parse_args as parse_research_args, report_stem
from backend_py.research.summary import build_summary_row, quality_summary


CliMain = Callable[[list[str] | None], None]
REPORT_KINDS = ("feature_factory", "deviation_rules", "market_weather_router")
GOLDEN_SYMBOLS = ["BTC-USDT", "SOL-USDT", "DOGE-USDT", "ENA-USDT"]
GOLDEN_BARS = ["1D", "4H", "8H", "1W"]
FIXTURE_CLEAN_DIR = PROJECT_ROOT / "tests" / "fixtures" / "data" / "clean"
GOLDEN_DIR = PROJECT_ROOT / "tests" / "golden"


def split_csv_values(values: list[str] | None) -> list[str]:
    return [item.strip() for value in values or [] for item in str(value).split(",") if item.strip()]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run frozen-golden Python research parity regression.")
    parser.add_argument("--symbols", nargs="*", help="Symbols to check. Defaults to the frozen fixture set.")
    parser.add_argument("--bars", nargs="*", default=[",".join(GOLDEN_BARS)], help="Bars to check. Defaults to 1D,4H,8H,1W.")
    parser.add_argument("--days", type=int, default=3650)
    parser.add_argument("--node-suffix", default="_node")
    parser.add_argument("--python-suffix", default="_py")
    parser.add_argument("--golden", action="store_true", help="Compatibility flag; frozen golden mode is always used.")
    parsed = parser.parse_args(argv)
    parsed.symbols = split_csv_values(parsed.symbols) or GOLDEN_SYMBOLS
    parsed.bars = split_csv_values(parsed.bars) or GOLDEN_BARS
    if parsed.python_suffix != "_py":
        parser.error("current Python parity builders write _py artifacts; keep --python-suffix _py")
    return parsed


def run_subprocess(command: list[str], label: str, *, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, cwd=PROJECT_ROOT, env=env or os.environ.copy(), text=True, capture_output=True, check=False)
    if result.returncode:
        tail = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-80:])
        raise RuntimeError(f"{label} failed with exitCode={result.returncode}\n{tail}")
    return result.stdout


def git_restore_reports() -> None:
    subprocess.run(["git", "restore", "reports"], cwd=PROJECT_ROOT, check=False)


def git_status_reports() -> str:
    result = subprocess.run(["git", "status", "--porcelain", "--", "reports"], cwd=PROJECT_ROOT, text=True, capture_output=True, check=False)
    return result.stdout.strip()


def require_clean_reports() -> None:
    dirty = git_status_reports()
    if dirty:
        raise RuntimeError(f"reports/ is not clean before parity check:\n{dirty}")


def remove_suffix_artifacts(*suffixes: str) -> int:
    removed = 0
    for suffix in suffixes:
        if not suffix:
            continue
        for extension in ("json", "csv"):
            for path in REPORTS_DIR.glob(f"*{suffix}.{extension}"):
                path.unlink(missing_ok=True)
                removed += 1
    return removed


def report_json_path(report_name: str, kind: str, suffix: str = "") -> Path:
    return REPORTS_DIR / f"{report_name}_{kind}{suffix}.json"


def summary_json_path(stem: str, suffix: str = "") -> Path:
    return REPORTS_DIR / f"{stem}{suffix}.json"


def copy_json(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def stage_frozen_golden(symbols: list[str], bars: list[str], days: int, suffix: str) -> dict[str, Any]:
    copied = 0
    missing: list[str] = []
    for bar in bars:
        for symbol in symbols:
            config = parse_research_args(["--instrument", symbol, "--bar", bar, "--days", str(days)])
            report_name = report_stem(config)
            for kind in REPORT_KINDS:
                source = GOLDEN_DIR / f"{report_name}_{kind}.json"
                target = report_json_path(report_name, kind, suffix)
                if not source.exists():
                    missing.append(str(source))
                    continue
                copy_json(source, target)
                copied += 1
    if missing:
        raise FileNotFoundError("missing frozen golden files:\n" + "\n".join(missing[:20]))
    return {"successCount": len(symbols) * len(bars), "errorCount": 0, "copiedJsonCount": copied, "source": str(GOLDEN_DIR)}


def run_cli(label: str, fn: CliMain, args: list[str], *, expect_ok: bool = True) -> dict[str, Any]:
    stdout = io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout):
            fn(args)
        return {"step": label, "status": "ok", "stdout": stdout.getvalue()}
    except SystemExit as error:
        status = "ok" if error.code == 0 else "failed"
        result = {"step": label, "status": status, "exitCode": error.code, "stdout": stdout.getvalue()}
        if expect_ok and status != "ok":
            return result
        return result
    except Exception as error:  # noqa: BLE001 - batch check should report scoped failures.
        return {"step": label, "status": "failed", "message": str(error), "stdout": stdout.getvalue()}


def scoped_args(symbol: str, bar: str, days: int) -> list[str]:
    return ["--instrument", symbol, "--bar", bar, "--days", str(days)]


def compare_args(symbol: str, bar: str, days: int, node_suffix: str, python_suffix: str) -> list[str]:
    return [*scoped_args(symbol, bar, days), "--node-suffix", node_suffix, "--python-suffix", python_suffix]


def build_python_shadows_from_fixture(symbols: list[str], bars: list[str], days: int, node_suffix: str, python_suffix: str) -> tuple[int, int, list[dict[str, Any]]]:
    passes = 0
    failures = 0
    failure_details: list[dict[str, Any]] = []
    env = os.environ.copy()
    env["RESEARCH_DATA_CLEAN_DIR"] = str(FIXTURE_CLEAN_DIR)
    builders = [
        ("feature", "backend_py.build_feature_factory", compare_feature_factory),
        ("deviation", "backend_py.build_deviation_rules", compare_deviation_rules),
        ("router", "backend_py.build_market_weather_router", compare_market_weather_router),
    ]
    for bar in bars:
        for symbol in symbols:
            args = scoped_args(symbol, bar, days)
            for label, module, compare_fn in builders:
                try:
                    run_subprocess([sys.executable, "-m", module, *args], f"{label}_build_fixture", env=env)
                except Exception as error:  # noqa: BLE001 - keep scoped failures visible.
                    failures += 1
                    failure_details.append({"instrument": symbol, "bar": bar, "step": f"{label}_build_fixture", "status": "failed", "message": str(error)})
                    continue
                compare_result = run_cli(f"{label}_compare", compare_fn, compare_args(symbol, bar, days, node_suffix, python_suffix))
                if compare_result["status"] == "ok":
                    passes += 1
                else:
                    failures += 1
                    failure_details.append({"instrument": symbol, "bar": bar, **compare_result})
    return passes, failures, failure_details


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n", encoding="utf-8")


def build_summary_from_suffix(symbols: list[str], bars: list[str], days: int, suffix: str, *, clean_dir: Path = FIXTURE_CLEAN_DIR) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    all_rows: list[dict[str, Any]] = []
    all_errors: list[dict[str, Any]] = []
    bar_summaries: list[dict[str, Any]] = []
    for bar in bars:
        rows: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for symbol in symbols:
            config: ResearchConfig = parse_research_args(["--instrument", symbol, "--bar", bar, "--days", str(days)])
            stem = file_stem(config)
            report_name = report_stem(config)
            try:
                clean_payload = read_json(clean_dir / f"{stem}_clean.json")
                feature_result = read_json(report_json_path(report_name, "feature_factory", suffix))
                weather_result = read_json(report_json_path(report_name, "market_weather_router", suffix))
                deviation_rules = read_json(report_json_path(report_name, "deviation_rules", suffix))
                rows.append(build_summary_row(config=config, clean_payload=clean_payload, feature_result=feature_result, weather_result=weather_result, deviation_rules=deviation_rules))
            except Exception as error:  # noqa: BLE001 - keep scoped summary errors.
                errors.append({"instrument": symbol, "bar": bar, "message": str(error)})
        quality = quality_summary(rows)
        write_json(
            summary_json_path(f"multi_{bar}_market_weather_current", suffix),
            {
                "metadata": {
                    "symbols": symbols,
                    "bar": bar,
                    "days": days,
                    "skipDownload": True,
                    "summaryOnly": True,
                    "fromReports": True,
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
        bar_summaries.append({"bar": bar, "successCount": len(rows), "errorCount": len(errors), "weightedWeatherCount": quality["weightedWeatherCount"]})
        all_rows.extend(rows)
        all_errors.extend(errors)
    combined_quality = quality_summary(all_rows)
    write_json(
        summary_json_path("multi_period_market_weather_current", suffix),
        {
            "metadata": {
                "symbols": symbols,
                "bars": bars,
                "skipDownload": True,
                "summaryOnly": True,
                "fromReports": True,
                "startedAt": started_at.isoformat().replace("+00:00", "Z"),
                "finishedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "successCount": len(all_rows),
                "weatherCount": combined_quality["weatherCount"],
                "weightedWeatherCount": combined_quality["weightedWeatherCount"],
                "averagePeriodWeight": combined_quality["averagePeriodWeight"],
                "lowWeightCount": combined_quality["lowWeightCount"],
                "insufficientHistoryCount": combined_quality["insufficientHistoryCount"],
                "errorCount": len(all_errors),
            },
            "rows": all_rows,
            "errors": all_errors,
        },
    )
    return {"successCount": len(all_rows), "errorCount": len(all_errors), "weightedWeatherCount": combined_quality["weightedWeatherCount"], "barSummaries": bar_summaries}


def run_check(parsed: argparse.Namespace) -> dict[str, Any]:
    remove_suffix_artifacts(parsed.node_suffix, parsed.python_suffix)
    require_clean_reports()
    baseline = stage_frozen_golden(parsed.symbols, parsed.bars, parsed.days, parsed.node_suffix)
    build_summary_from_suffix(parsed.symbols, parsed.bars, parsed.days, parsed.node_suffix, clean_dir=FIXTURE_CLEAN_DIR)
    passes, failures, failure_details = build_python_shadows_from_fixture(parsed.symbols, parsed.bars, parsed.days, parsed.node_suffix, parsed.python_suffix)
    python_summary = build_summary_from_suffix(parsed.symbols, parsed.bars, parsed.days, parsed.python_suffix, clean_dir=FIXTURE_CLEAN_DIR)
    summary_result = run_cli(
        "summary_compare",
        compare_summary,
        ["--symbols", ",".join(parsed.symbols), "--bars", ",".join(parsed.bars), "--days", str(parsed.days), "--node-suffix", parsed.node_suffix, "--python-suffix", parsed.python_suffix],
    )
    if summary_result["status"] != "ok":
        failure_details.append(summary_result)
    return {
        "step": "python-official-parity-regression",
        "mode": "frozen-golden",
        "symbols": parsed.symbols,
        "bars": parsed.bars,
        "baseline": baseline,
        "pythonSummary": python_summary,
        "PASS": passes,
        "FAIL": failures,
        "summaryStatus": summary_result["status"],
        "failures": failure_details[:50],
    }


def cleanup(node_suffix: str, python_suffix: str) -> dict[str, Any]:
    git_restore_reports()
    removed = remove_suffix_artifacts(node_suffix, python_suffix)
    dirty = git_status_reports()
    return {"restoredReports": not dirty, "removedTempArtifacts": removed, "reportsStatus": dirty}


def main(argv: list[str] | None = None) -> None:
    parsed = parse_args(list(argv if argv is not None else sys.argv[1:]))
    result: dict[str, Any] | None = None
    exit_code = 0
    try:
        result = run_check(parsed)
        exit_code = 0 if result["FAIL"] == 0 and result["summaryStatus"] == "ok" else 1
    except KeyboardInterrupt:
        result = {"step": "python-official-parity-regression", "status": "interrupted"}
        exit_code = 130
    except Exception as error:  # noqa: BLE001 - emit cleanup info before failing.
        result = {"step": "python-official-parity-regression", "status": "failed", "message": str(error)}
        exit_code = 1
    finally:
        cleanup_result = cleanup(parsed.node_suffix, parsed.python_suffix)
        if result is not None:
            result["cleanup"] = cleanup_result
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if "PASS" in result and "FAIL" in result:
                print(f"PASS={result['PASS']} FAIL={result['FAIL']}")
                print(f"SUMMARY={result.get('summaryStatus')}")
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
