from __future__ import annotations

from backend_py.main import (
    clean_candles,
    dashboard_current,
    health,
    market_current,
    market_overview,
    report_json,
    scanner_status,
)


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
