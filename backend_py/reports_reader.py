from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = PROJECT_ROOT / "reports"
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_CLEAN_DIR = Path(os.environ.get("RESEARCH_DATA_CLEAN_DIR") or (PROJECT_ROOT / "data" / "clean"))
MULTI_PERIOD_REPORT = "multi_period_market_weather_current.json"
REPORT_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+\.json$")
SYMBOL_RE = re.compile(r"^[A-Z0-9]+-[A-Z0-9]+$")
BAR_RE = re.compile(r"^[0-9A-Z]+$")
DASHBOARD_BARS = {"1D", "4H", "8H", "1W"}


class ReportNotFound(FileNotFoundError):
    pass


def normalize_instrument(value: str | None) -> str | None:
    if not value:
        return None
    symbol = value.strip().upper().replace("_", "-").replace("/", "-")
    if "-" not in symbol and symbol.endswith("USDT"):
        return f"{symbol[:-4]}-USDT"
    return symbol


def normalize_bar(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().upper()


def report_stem(instrument: str, bar: str, *, allowed_bars: set[str] | None = None) -> str:
    normalized_instrument = normalize_instrument(instrument)
    normalized_bar = normalize_bar(bar)
    if not normalized_instrument or not SYMBOL_RE.fullmatch(normalized_instrument):
        raise ValueError("Invalid instrument")
    if not normalized_bar or not BAR_RE.fullmatch(normalized_bar):
        raise ValueError("Invalid bar")
    if allowed_bars is not None and normalized_bar not in allowed_bars:
        raise ValueError(f"Unsupported bar: {normalized_bar}")
    return f"{normalized_instrument.replace('-', '_')}_{normalized_bar}"


def file_mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts = Counter(str(row.get(key) or "unknown") for row in rows)
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


class ReportsReader:
    def __init__(self, reports_dir: Path | None = None, clean_dir: Path | None = None) -> None:
        self.reports_dir = reports_dir or REPORTS_DIR
        self.clean_dir = clean_dir or DATA_CLEAN_DIR

    @property
    def multi_period_path(self) -> Path:
        return self.reports_dir / MULTI_PERIOD_REPORT

    def load_json_report(self, name: str) -> dict[str, Any]:
        if not REPORT_NAME_RE.fullmatch(name):
            raise ValueError("Invalid report name")
        path = self.reports_dir / name
        if path.parent != self.reports_dir or path.suffix.lower() != ".json":
            raise ValueError("Only top-level JSON reports are allowed")
        if not path.exists():
            raise ReportNotFound(f"Report not found: {name}")
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if isinstance(payload, dict):
            payload.setdefault("_source", {})
            payload["_source"].update(
                {
                    "reportName": name,
                    "reportPath": str(path),
                    "reportMtime": file_mtime_iso(path),
                }
            )
        return payload

    def load_clean_candles(self, instrument: str, bar: str) -> dict[str, Any]:
        stem = report_stem(instrument, bar)
        name = f"{stem}_clean.json"
        path = self.clean_dir / name
        if path.parent != self.clean_dir or path.suffix.lower() != ".json":
            raise ValueError("Only top-level clean JSON files are allowed")
        if not path.exists():
            raise ReportNotFound(f"Clean candles not found: {name}")
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if isinstance(payload, dict):
            payload.setdefault("_source", {})
            payload["_source"].update(
                {
                    "reportName": name,
                    "reportPath": str(path),
                    "reportMtime": file_mtime_iso(path),
                }
            )
        return payload

    def load_dashboard(self, instrument: str, bar: str) -> dict[str, Any]:
        normalized_instrument = normalize_instrument(instrument)
        normalized_bar = normalize_bar(bar)
        stem = report_stem(instrument, bar, allowed_bars=DASHBOARD_BARS)

        weather_name = f"{stem}_market_weather_router.json"
        features_name = f"{stem}_feature_factory.json"
        deviations_name = f"{stem}_deviation_rules.json"
        candles_name = f"{stem}_clean.json"

        weather = self.load_json_report(weather_name)
        features = self.load_json_report(features_name)

        sources: dict[str, dict[str, Any]] = {
            "weather": {"status": "ok", "name": weather_name},
            "features": {"status": "ok", "name": features_name},
            "deviations": {"status": "ok", "name": deviations_name},
            "candles": {"status": "ok", "name": candles_name},
        }

        try:
            deviations: dict[str, Any] | None = self.load_json_report(deviations_name)
        except ReportNotFound:
            deviations = None
            sources["deviations"]["status"] = "missing_optional"

        try:
            candles: dict[str, Any] | None = self.load_clean_candles(normalized_instrument or instrument, normalized_bar or bar)
        except ReportNotFound:
            candles = None
            sources["candles"]["status"] = "missing_optional"

        return {
            "instrument": normalized_instrument,
            "bar": normalized_bar,
            "sources": sources,
            "weather": weather,
            "features": features,
            "deviations": deviations,
            "candles": candles,
        }

    def load_multi_period(self) -> dict[str, Any]:
        return self.load_json_report(MULTI_PERIOD_REPORT)

    def metadata(self) -> dict[str, Any]:
        payload = self.load_multi_period()
        metadata = dict(payload.get("metadata") or {})
        metadata["sourceReport"] = payload.get("_source", {})
        return metadata

    def rows(
        self,
        *,
        instrument: str | None = None,
        bar: str | None = None,
        gate: str | None = None,
        data_status: str | None = None,
    ) -> list[dict[str, Any]]:
        payload = self.load_multi_period()
        rows = list(payload.get("rows") or [])
        expected_instrument = normalize_instrument(instrument)
        expected_bar = normalize_bar(bar)

        if expected_instrument:
            rows = [row for row in rows if normalize_instrument(row.get("instrument")) == expected_instrument]
        if expected_bar:
            rows = [row for row in rows if normalize_bar(row.get("bar")) == expected_bar]
        if gate:
            rows = [row for row in rows if str(row.get("gate") or "") == gate]
        if data_status:
            rows = [row for row in rows if str(row.get("dataStatus") or "") == data_status]
        return rows

    def current(self, instrument: str, bar: str = "4H") -> dict[str, Any] | None:
        rows = self.rows(instrument=instrument, bar=bar)
        if not rows:
            return None
        return rows[0]

    def symbols(self) -> list[str]:
        metadata = self.metadata()
        symbols = metadata.get("symbols") or []
        if symbols:
            return sorted(normalize_instrument(symbol) or symbol for symbol in symbols)
        return sorted({row["instrument"] for row in self.rows() if row.get("instrument")})

    def overview(self) -> dict[str, Any]:
        payload = self.load_multi_period()
        rows = list(payload.get("rows") or [])
        bars = sorted({str(row.get("bar")) for row in rows if row.get("bar")})
        symbols = sorted({str(row.get("instrument")) for row in rows if row.get("instrument")})
        by_bar: dict[str, Any] = {}
        for bar in bars:
            bar_rows = [row for row in rows if str(row.get("bar")) == bar]
            by_bar[bar] = {
                "rowCount": len(bar_rows),
                "gateCounts": count_by(bar_rows, "gate"),
                "dataStatusCounts": count_by(bar_rows, "dataStatus"),
                "volatilityStateCounts": count_by(bar_rows, "volatilityState"),
                "lowWeightCount": sum(1 for row in bar_rows if float(row.get("periodWeight") or 0) < 1),
            }

        return {
            "metadata": payload.get("metadata") or {},
            "sourceReport": payload.get("_source", {}),
            "rowCount": len(rows),
            "symbolCount": len(symbols),
            "symbols": symbols,
            "bars": bars,
            "gateCounts": count_by(rows, "gate"),
            "dataStatusCounts": count_by(rows, "dataStatus"),
            "volatilityStateCounts": count_by(rows, "volatilityState"),
            "byBar": by_bar,
        }
