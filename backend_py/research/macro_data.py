from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .feature_factory import finite, js_round, safe_divide


FRED_SOURCES = [
    {
        "key": "dollarIndex",
        "id": "DTWEXBGS",
        "label": "美元指数代理",
        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS",
    },
    {
        "key": "us10y",
        "id": "DGS10",
        "label": "美国10年国债收益率",
        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10",
    },
    {
        "key": "fedFunds",
        "id": "DFF",
        "label": "有效联邦基金利率",
        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF",
    },
    {
        "key": "m2",
        "id": "M2SL",
        "label": "M2货币供应",
        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=M2SL",
    },
]

STABLECOIN_SOURCE = {
    "key": "stablecoinSupply",
    "label": "稳定币总供应",
    "url": "https://stablecoins.llama.fi/stablecoincharts/all",
}

MACRO_FEATURE_DEFS = [
    {"key": "macroDollarIndex", "label": "美元指数代理"},
    {"key": "macroDollarIndex21dChangePct", "label": "美元指数21日变化率"},
    {"key": "macroUs10y", "label": "10年美债收益率"},
    {"key": "macroUs10y21dChangeBp", "label": "10年美债21日变化bp"},
    {"key": "macroFedFunds", "label": "联邦基金利率"},
    {"key": "macroFedFunds63dChangeBp", "label": "联邦基金利率63日变化bp"},
    {"key": "macroM2", "label": "M2货币供应"},
    {"key": "macroM263dChangePct", "label": "M2 63日变化率"},
    {"key": "macroStablecoinSupply", "label": "稳定币总供应"},
    {"key": "macroStablecoin63dChangePct", "label": "稳定币63日变化率"},
    {"key": "macroRiskPressureScore", "label": "宏观风险压力"},
    {"key": "macroLiquidityScore", "label": "宏观流动性评分"},
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_number(value: Any) -> float | None:
    if value is None or value == "" or value == ".":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if finite(parsed) else None


def date_from_timestamp(value: Any) -> str | None:
    parsed = parse_number(value)
    if parsed is None:
        return None
    seconds = parsed / 1000 if parsed > 10_000_000_000 else parsed
    return datetime.fromtimestamp(seconds, timezone.utc).date().isoformat()


def parse_fred_csv(text: str, source: dict[str, str]) -> list[dict[str, Any]]:
    lines = [line for line in text.strip().splitlines() if line]
    if not lines:
        return []
    header = lines.pop(0).split(",")
    if len(header) < 2:
        return []
    rows = []
    for line in lines:
        parts = line.split(",")
        if len(parts) < 2:
            continue
        date, value = parts[0], parts[1]
        parsed = parse_number(value)
        if date and parsed is not None:
            rows.append({"date": date, "key": source["key"], "value": parsed})
    return rows


def parse_stablecoin_chart(payload: Any) -> list[dict[str, Any]]:
    rows = payload if isinstance(payload, list) else []
    parsed_rows = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        raw_date = item.get("date")
        date = raw_date[:10] if isinstance(raw_date, str) else date_from_timestamp(raw_date)
        raw_value = (
            ((item.get("totalCirculatingUSD") or {}).get("peggedUSD") if isinstance(item.get("totalCirculatingUSD"), dict) else item.get("totalCirculatingUSD"))
            or ((item.get("totalCirculating") or {}).get("peggedUSD") if isinstance(item.get("totalCirculating"), dict) else item.get("totalCirculating"))
        )
        value = parse_number(raw_value)
        if date and value is not None:
            parsed_rows.append({"date": date, "key": STABLECOIN_SOURCE["key"], "value": value})
    return parsed_rows


def series_value_on_or_before(series_rows: list[dict[str, Any]], date: str, cursor: dict[str, int]) -> float | None:
    while cursor["index"] + 1 < len(series_rows) and series_rows[cursor["index"] + 1]["date"] <= date:
        cursor["index"] += 1
    return series_rows[cursor["index"]]["value"] if cursor["index"] >= 0 else None


def value_ago(rows: list[dict[str, Any]], index: int, lookback: int, key: str) -> float | None:
    target_index = index - lookback
    if target_index < 0:
        return None
    return rows[target_index].get(key)


def pct_change(current: float | None, previous: float | None) -> float | None:
    if not finite(current) or not finite(previous) or previous == 0:
        return None
    return ((current - previous) / previous) * 100


def bp_change(current: float | None, previous: float | None) -> float | None:
    if not finite(current) or not finite(previous):
        return None
    return (current - previous) * 100


def macro_round(value: float | None) -> float | None:
    return js_round(value, 6) if finite(value) else None


def build_macro_feature_rows(candle_dates: list[str], source_rows_by_key: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    source_cursors = {
        key: {"index": -1, "rows": sorted(rows, key=lambda row: row["date"])}
        for key, rows in source_rows_by_key.items()
    }
    rows = []
    for date in sorted(candle_dates):
        rows.append(
            {
                "date": date,
                "macroDollarIndex": series_value_on_or_before(source_cursors.get("dollarIndex", {"index": -1, "rows": []})["rows"], date, source_cursors.get("dollarIndex", {"index": -1})),
                "macroUs10y": series_value_on_or_before(source_cursors.get("us10y", {"index": -1, "rows": []})["rows"], date, source_cursors.get("us10y", {"index": -1})),
                "macroFedFunds": series_value_on_or_before(source_cursors.get("fedFunds", {"index": -1, "rows": []})["rows"], date, source_cursors.get("fedFunds", {"index": -1})),
                "macroM2": series_value_on_or_before(source_cursors.get("m2", {"index": -1, "rows": []})["rows"], date, source_cursors.get("m2", {"index": -1})),
                "macroStablecoinSupply": series_value_on_or_before(source_cursors.get("stablecoinSupply", {"index": -1, "rows": []})["rows"], date, source_cursors.get("stablecoinSupply", {"index": -1})),
            }
        )

    feature_rows = []
    for index, row in enumerate(rows):
        dollar_change = pct_change(row["macroDollarIndex"], value_ago(rows, index, 21, "macroDollarIndex"))
        us10y_change = bp_change(row["macroUs10y"], value_ago(rows, index, 21, "macroUs10y"))
        fed_funds_change = bp_change(row["macroFedFunds"], value_ago(rows, index, 63, "macroFedFunds"))
        m2_change = pct_change(row["macroM2"], value_ago(rows, index, 63, "macroM2"))
        stablecoin_change = pct_change(row["macroStablecoinSupply"], value_ago(rows, index, 63, "macroStablecoinSupply"))
        risk_pressure = (
            (dollar_change or 0)
            + safe_divide(us10y_change or 0, 25)
            + safe_divide(fed_funds_change or 0, 25)
            - safe_divide(m2_change or 0, 2)
            - safe_divide(stablecoin_change or 0, 2)
        )
        feature_rows.append(
            {
                "date": row["date"],
                "macroDollarIndex": macro_round(row["macroDollarIndex"]),
                "macroDollarIndex21dChangePct": macro_round(dollar_change),
                "macroUs10y": macro_round(row["macroUs10y"]),
                "macroUs10y21dChangeBp": macro_round(us10y_change),
                "macroFedFunds": macro_round(row["macroFedFunds"]),
                "macroFedFunds63dChangeBp": macro_round(fed_funds_change),
                "macroM2": macro_round(row["macroM2"]),
                "macroM263dChangePct": macro_round(m2_change),
                "macroStablecoinSupply": macro_round(row["macroStablecoinSupply"]),
                "macroStablecoin63dChangePct": macro_round(stablecoin_change),
                "macroRiskPressureScore": macro_round(risk_pressure),
                "macroLiquidityScore": macro_round(-risk_pressure),
            }
        )
    return feature_rows


def macro_rows_to_csv_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "date": row["date"],
            **{feature["key"]: row.get(feature["key"]) if row.get(feature["key"]) is not None else "" for feature in MACRO_FEATURE_DEFS},
        }
        for row in rows
    ]
