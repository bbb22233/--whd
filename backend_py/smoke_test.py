from __future__ import annotations

from backend_py.main import health, market_current, market_overview, scanner_status


def main() -> None:
    health_payload = health()
    assert health_payload["multiPeriodReportExists"] is True

    overview_payload = market_overview()
    assert overview_payload["rowCount"] > 0
    assert "4H" in overview_payload["bars"]

    btc_payload = market_current("BTC-USDT", bar="4H")
    assert btc_payload["row"]["instrument"] == "BTC-USDT"
    assert btc_payload["row"]["bar"] == "4H"

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
        }
    )


if __name__ == "__main__":
    main()
