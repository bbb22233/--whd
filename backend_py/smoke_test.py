from __future__ import annotations

import json
from pathlib import Path

from backend_py.main import (
    clean_candles,
    dashboard_current,
    health,
    market_current,
    market_overview,
    report_json,
    scanner_status,
)
from backend_py.run_full_pipeline import output_plan, parse_batch_args
from backend_py.scanner_service import command_for_mode


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def optional_clean_candle_count(instrument: str, bar: str) -> tuple[str, int | None]:
    try:
        candles_payload = clean_candles(instrument, bar)
    except Exception as error:  # noqa: BLE001 - route helpers raise HTTPException outside ASGI.
        if getattr(error, "status_code", None) == 404:
            return "missing_untracked_data", None
        raise

    candle_count = len(candles_payload["candles"])
    assert candle_count > 0
    return "ok", candle_count


def main() -> None:
    health_payload = health()
    assert health_payload["multiPeriodReportExists"] is True

    overview_payload = market_overview()
    assert overview_payload["rowCount"] > 0
    assert "4H" in overview_payload["bars"]

    btc_payload = market_current("BTC-USDT", bar="4H")
    assert btc_payload["row"]["instrument"] == "BTC-USDT"
    assert btc_payload["row"]["bar"] == "4H"

    report_payload = report_json("BTC_USDT_1D_market_weather_router.json")
    assert report_payload["metadata"]["instrument"] == "BTC-USDT"

    dashboard_payload = dashboard_current("BTC-USDT", "1D")
    assert dashboard_payload["instrument"] == "BTC-USDT"
    assert dashboard_payload["bar"] == "1D"
    assert dashboard_payload["sources"]["weather"]["status"] == "ok"
    assert dashboard_payload["sources"]["features"]["status"] == "ok"
    assert dashboard_payload["weather"]["metadata"]["instrument"] == "BTC-USDT"
    assert dashboard_payload["features"]["metadata"]["instrument"] == "BTC-USDT"
    assert dashboard_payload["sources"]["candles"]["status"] in {"ok", "missing_optional"}

    clean_status, clean_candle_count = optional_clean_candle_count("BTC-USDT", "1D")

    scanner_payload = scanner_status()
    assert scanner_payload["mode"] == "python_orchestrator"
    assert scanner_payload["scanner"]["active"] is False
    assert "summary" in scanner_payload["scanner"]["supportedModes"]
    assert "python_summary" in scanner_payload["scanner"]["supportedModes"]
    assert "python_router" in scanner_payload["scanner"]["supportedModes"]
    assert "python_research" in scanner_payload["scanner"]["supportedModes"]
    assert "python_data" in scanner_payload["scanner"]["supportedModes"]
    assert "python_full" in scanner_payload["scanner"]["supportedModes"]
    assert "node_summary" in scanner_payload["scanner"]["supportedModes"]
    assert "node_full" in scanner_payload["scanner"]["supportedModes"]
    summary_command = command_for_mode("summary")
    assert "backend_py.run_full_pipeline" in summary_command
    assert "--from-reports" in summary_command
    assert "--summary-only" in summary_command
    assert "--skip-download" in summary_command
    assert "--official" in summary_command
    assert summary_command[-2:] == ["--bars", "1D,4H,8H"]
    full_command = command_for_mode("full")
    assert "backend_py.run_full_pipeline" in full_command
    assert "--skip-download" in full_command
    assert "--official" in full_command
    assert full_command[-2:] == ["--bars", "1D,4H,8H"]
    assert "legacy:multi:periods" in command_for_mode("node_summary")
    assert "legacy:multi:periods" in command_for_mode("node_full")
    assert "backend_py.build_summary" in command_for_mode("python_summary")
    assert "backend_py.run_router_parity" in command_for_mode("python_router")
    assert "backend_py.run_research_parity" in command_for_mode("python_research")
    assert "backend_py.run_data_pipeline" in command_for_mode("python_data")
    assert "backend_py.run_full_pipeline" in command_for_mode("python_full")

    package_scripts = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
    assert "backend_py.run_full_pipeline" in package_scripts["multi:periods"]
    assert "--official" in package_scripts["multi:periods"]
    assert "--bars \"1D,4H,8H\"" in package_scripts["multi:periods"]
    assert "backend_py.run_full_pipeline" in package_scripts["multi:summary"]
    assert "--summary-only" in package_scripts["multi:summary"]
    assert "scripts/run-multi-symbol-1d.mjs" in package_scripts["legacy:multi:periods"]
    assert "scripts/run-multi-symbol-1d.mjs" in package_scripts["legacy:multi:1d"]

    scoped_summary = command_for_mode("summary", symbols="BTC-USDT,ETH-USDT", bars="1D,4H")
    assert scoped_summary[-5:] == ["--symbols", "BTC-USDT", "ETH-USDT", "--bars", "1D,4H"]
    scoped_python_summary = command_for_mode("python_summary", symbols="BTC-USDT,ETH-USDT", bars="1D,4H")
    assert scoped_python_summary[-5:] == ["--symbols", "BTC-USDT", "ETH-USDT", "--bars", "1D,4H"]
    scoped_python_router = command_for_mode("python_router", symbols="BTC-USDT,ETH-USDT", bars="1D,4H")
    assert scoped_python_router[-5:] == ["--symbols", "BTC-USDT", "ETH-USDT", "--bars", "1D,4H"]
    scoped_python_research = command_for_mode("python_research", symbols="BTC-USDT,ETH-USDT", bars="1D,4H")
    assert scoped_python_research[-5:] == ["--symbols", "BTC-USDT", "ETH-USDT", "--bars", "1D,4H"]
    scoped_python_data = command_for_mode("python_data", symbols="BTC-USDT,ETH-USDT", bars="1D,4H")
    assert scoped_python_data[-5:] == ["--symbols", "BTC-USDT", "ETH-USDT", "--bars", "1D,4H"]
    scoped_full = command_for_mode("full", symbols="BTC-USDT,ETH-USDT", bars="1D,4H")
    assert scoped_full[-5:] == ["--symbols", "BTC-USDT", "ETH-USDT", "--bars", "1D,4H"]
    scoped_python_full = command_for_mode("python_full", symbols="BTC-USDT,ETH-USDT", bars="1D,4H")
    assert scoped_python_full[-5:] == ["--symbols", "BTC-USDT", "ETH-USDT", "--bars", "1D,4H"]
    plan_args = parse_batch_args(["--symbols", "BTC-USDT", "ETH-USDT", "--bars", "1D,4H", "--official", "--plan-outputs"])
    plan_payload = output_plan(
        plan_args["config"],
        plan_args["symbols"],
        plan_args["bars"],
        official=plan_args["official"],
        summary_only=plan_args["summaryOnly"],
        from_reports=plan_args["fromReports"],
    )
    assert plan_payload["step"] == "python-full-output-plan"
    assert plan_payload["official"] is True
    assert plan_payload["suffix"] == ""
    assert plan_payload["pathCount"] == 46

    print(
        {
            "health": health_payload["status"],
            "rowCount": overview_payload["rowCount"],
            "symbolCount": overview_payload["symbolCount"],
            "btc4hGate": btc_payload["row"].get("gate"),
            "scannerMode": scanner_payload["mode"],
            "compatReport": report_payload["metadata"].get("bar"),
            "dashboardCandlesStatus": dashboard_payload["sources"]["candles"]["status"],
            "cleanCandles": clean_candle_count,
            "cleanCandlesStatus": clean_status,
        }
    )


if __name__ == "__main__":
    main()
