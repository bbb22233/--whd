from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


DAY_MS = 24 * 60 * 60 * 1000
HOUR_MS = 60 * 60 * 1000


def finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and value == value and value not in {float("inf"), float("-inf")}


def bar_to_ms(bar: str | None) -> int:
    text = str(bar or "1D")
    try:
        value = int("".join(char for char in text if char.isdigit()) or "1")
    except ValueError:
        value = 1
    if text.endswith("m"):
        return value * 60 * 1000
    if text.endswith("H"):
        return value * HOUR_MS
    if text.endswith("D"):
        return value * DAY_MS
    if text.endswith("W"):
        return value * 7 * DAY_MS
    return DAY_MS


def iso_from_ms(open_time: int | float) -> str:
    return datetime.fromtimestamp(float(open_time) / 1000, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def format_candle_date(open_time: int | float, bar: str | None) -> str:
    iso = iso_from_ms(open_time)
    if bar_to_ms(bar) < DAY_MS:
        return iso[:16].replace("T", " ")
    return iso[:10]


def to_number(value: Any) -> float:
    if value in {None, ""}:
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def normalize_number(value: float) -> int | float:
    return int(value) if finite(value) and float(value).is_integer() else value


def normalize_row(row: list[Any], bar: str) -> dict[str, Any]:
    open_time = to_number(row[0] if len(row) > 0 else None)
    duration = bar_to_ms(bar)
    candle = {
        "openTime": normalize_number(open_time),
        "closeTime": normalize_number(open_time + duration - 1),
        "date": format_candle_date(open_time, bar) if finite(open_time) else "Invalid Date",
        "open": normalize_number(to_number(row[1] if len(row) > 1 else None)),
        "high": normalize_number(to_number(row[2] if len(row) > 2 else None)),
        "low": normalize_number(to_number(row[3] if len(row) > 3 else None)),
        "close": normalize_number(to_number(row[4] if len(row) > 4 else None)),
        "volume": normalize_number(to_number(row[7] if len(row) > 7 and row[7] else row[5] if len(row) > 5 else None)),
        "confirm": "1" if len(row) <= 8 else str(row[8]),
    }
    return candle


def is_structurally_valid_candle(candle: dict[str, Any]) -> bool:
    return (
        finite(candle.get("openTime"))
        and finite(candle.get("open"))
        and finite(candle.get("high"))
        and finite(candle.get("low"))
        and finite(candle.get("close"))
        and finite(candle.get("volume"))
        and candle["open"] > 0
        and candle["high"] > 0
        and candle["low"] > 0
        and candle["close"] > 0
        and candle["high"] >= max(candle["open"], candle["close"])
        and candle["low"] <= min(candle["open"], candle["close"])
    )


def is_extreme_candle(candle: dict[str, Any]) -> bool:
    high_low_ratio = candle["high"] / candle["low"]
    open_close_ratio = max(candle["open"], candle["close"]) / min(candle["open"], candle["close"])
    return high_low_ratio > 5 or open_close_ratio > 5


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def clean_okx_raw(raw_payload: dict[str, Any]) -> dict[str, Any]:
    seen: dict[Any, dict[str, Any]] = {}
    invalid_rows = []
    duplicate_rows = 0
    extreme_rows = 0
    unconfirmed_rows = 0
    bar = raw_payload.get("bar") or "1D"
    bar_ms = bar_to_ms(bar)
    truncation_known = isinstance(raw_payload.get("truncated"), bool)
    legacy_page_limit_hit = not truncation_known and raw_payload.get("bar") == "4H" and float(raw_payload.get("pageCount") or 0) >= 80
    truncated = bool(raw_payload.get("truncated")) if truncation_known else legacy_page_limit_hit

    for row in raw_payload.get("rows") or []:
        candle = normalize_row(row, bar)
        if candle["confirm"] != "1":
            unconfirmed_rows += 1
            continue
        if not is_structurally_valid_candle(candle):
            invalid_rows.append(row)
            continue
        if is_extreme_candle(candle):
            candle["extremeFlag"] = True
            extreme_rows += 1
        if candle["openTime"] in seen:
            duplicate_rows += 1
        seen[candle["openTime"]] = candle

    candles = sorted(seen.values(), key=lambda item: item["openTime"])
    missing_bars = []
    for index in range(1, len(candles)):
        gap = candles[index]["openTime"] - candles[index - 1]["openTime"]
        if gap > bar_ms * 1.5:
            missing_bars.append(
                {
                    "previousDate": candles[index - 1]["date"],
                    "nextDate": candles[index]["date"],
                    "missingBars": round(gap / bar_ms) - 1,
                }
            )

    return {
        "metadata": {
            "source": raw_payload.get("source"),
            "instrument": raw_payload.get("instrument"),
            "bar": raw_payload.get("bar"),
            "requestedDays": raw_payload.get("requestedDays"),
            "requestedStartMs": raw_payload.get("requestedStartMs"),
            "requestedStartDate": raw_payload.get("requestedStartDate"),
            "downloadedAt": raw_payload.get("downloadedAt"),
            "pageCount": raw_payload.get("pageCount"),
            "requestLimit": raw_payload.get("requestLimit"),
            "maxPages": raw_payload.get("maxPages"),
            "retryCount": raw_payload.get("retryCount"),
            "oldestReached": raw_payload.get("oldestReached"),
            "oldestReachedDate": raw_payload.get("oldestReachedDate"),
            "truncated": truncated,
            "truncationKnown": truncation_known,
            "truncationReason": "legacy_page_limit" if legacy_page_limit_hit and truncated else "requested_start_not_reached" if truncated else None,
            "cleanedAt": utc_now_iso(),
            "rawRows": len(raw_payload.get("rows") or []),
            "cleanRows": len(candles),
            "duplicateRows": duplicate_rows,
            "invalidRows": len(invalid_rows),
            "extremeRows": extreme_rows,
            "unconfirmedRows": unconfirmed_rows,
            "missingBars": missing_bars,
            "firstDate": candles[0]["date"] if candles else None,
            "lastDate": candles[-1]["date"] if candles else None,
        },
        "candles": candles,
    }


def candles_to_csv_rows(candles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "date": candle.get("date"),
            "openTime": candle.get("openTime"),
            "open": candle.get("open"),
            "high": candle.get("high"),
            "low": candle.get("low"),
            "close": candle.get("close"),
            "volume": candle.get("volume"),
        }
        for candle in candles
    ]
