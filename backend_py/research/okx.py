from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend_py.research.clean import DAY_MS, HOUR_MS, bar_to_ms
from backend_py.research.config import ResearchConfig


OKX_HISTORY_CANDLES_URL = "https://www.okx.com/api/v5/market/history-candles"
DEFAULT_REQUEST_LIMIT = 100
PAGE_SAFETY_MULTIPLIER = 1.2
PAGE_SAFETY_EXTRA = 3
RETRY_DELAYS_SECONDS = [2, 4, 8, 16]


def timestamp_to_iso(timestamp: int | float | None) -> str | None:
    if timestamp is None or not math.isfinite(float(timestamp)):
        return None
    return datetime.fromtimestamp(float(timestamp) / 1000, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def row_timestamp(row: Any) -> float:
    try:
        return float(row[0])
    except (TypeError, ValueError, IndexError):
        return float("nan")


def calculate_max_pages(config: ResearchConfig) -> dict[str, int]:
    request_limit = max(1, math.floor(float(config.requestLimit or DEFAULT_REQUEST_LIMIT)))
    requested_bars = math.ceil((config.days * DAY_MS) / bar_to_ms(config.bar))
    max_pages = max(1, math.ceil((requested_bars / request_limit) * PAGE_SAFETY_MULTIPLIER) + PAGE_SAFETY_EXTRA)
    return {"requestLimit": request_limit, "maxPages": max_pages}


def fetch_okx_page(url: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(len(RETRY_DELAYS_SECONDS) + 1):
        try:
            request = Request(url, headers={"User-Agent": "whd-python-research/1.0"})
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("code") != "0" or not isinstance(payload.get("data"), list):
                raise RuntimeError(f"OKX response unavailable: {payload.get('msg') or payload.get('code') or 'unknown'}")
            return {"payload": payload, "retryCount": attempt}
        except Exception as error:  # noqa: BLE001 - retry wrapper returns final upstream error.
            last_error = error
            if attempt >= len(RETRY_DELAYS_SECONDS):
                break
            time.sleep(RETRY_DELAYS_SECONDS[attempt])
    raise RuntimeError(str(last_error))


def download_okx_history(config: ResearchConfig) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    start_ms = int(started_at.timestamp() * 1000) - config.days * HOUR_MS * 24
    page_config = calculate_max_pages(config)
    request_limit = page_config["requestLimit"]
    max_pages = page_config["maxPages"]
    rows_by_time: dict[str, list[Any]] = {}
    cursor: str | None = None
    page = 0
    last_oldest = float("inf")
    oldest_reached: float | None = None
    retry_count = 0

    while page < max_pages:
        query = {"instId": config.instrument, "bar": config.bar, "limit": str(request_limit)}
        if cursor:
            query["after"] = cursor
        page_result = fetch_okx_page(f"{OKX_HISTORY_CANDLES_URL}?{urlencode(query)}")
        retry_count += int(page_result["retryCount"])

        page_rows = [row for row in page_result["payload"]["data"] if math.isfinite(row_timestamp(row))]
        if not page_rows:
            break

        for row in page_rows:
            rows_by_time[str(int(row_timestamp(row)))] = row

        oldest = min(row_timestamp(row) for row in page_rows)
        oldest_reached = oldest if oldest_reached is None else min(oldest_reached, oldest)
        page += 1

        if oldest <= start_ms or oldest >= last_oldest:
            break
        last_oldest = oldest
        cursor = str(int(oldest))
        time.sleep(0.14)

    rows = [
        row
        for row in sorted(rows_by_time.values(), key=row_timestamp)
        if row_timestamp(row) >= start_ms
    ]
    truncated = oldest_reached is None or oldest_reached > start_ms
    return {
        "source": "OKX",
        "endpoint": OKX_HISTORY_CANDLES_URL,
        "instrument": config.instrument,
        "bar": config.bar,
        "requestedDays": config.days,
        "requestedStartMs": start_ms,
        "requestedStartDate": timestamp_to_iso(start_ms),
        "requestLimit": request_limit,
        "maxPages": max_pages,
        "downloadedAt": utc_now_iso(),
        "pageCount": page,
        "rowCount": len(rows),
        "retryCount": retry_count,
        "oldestReached": int(oldest_reached) if oldest_reached is not None else None,
        "oldestReachedDate": timestamp_to_iso(oldest_reached),
        "truncated": truncated,
        "rows": rows,
    }
