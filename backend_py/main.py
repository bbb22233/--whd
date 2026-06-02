from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .reports_reader import ReportNotFound, ReportsReader, normalize_bar, normalize_instrument


app = FastAPI(
    title="Quant Monitor Python Backend",
    version="0.1.0",
    description="Python API layer for market weather reports.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:4177", "http://localhost:4177"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

reader = ReportsReader()


def sort_rows(
    rows: list[dict[str, Any]],
    sort: Literal["instrument", "bar", "date", "periodWeight", "topWeatherScore"] = "instrument",
    order: Literal["asc", "desc"] = "asc",
) -> list[dict[str, Any]]:
    reverse = order == "desc"

    def sort_key(row: dict[str, Any]) -> tuple[int, Any]:
        value = row.get(sort)
        if value is None:
            return (1, "")
        return (0, value)

    return sorted(rows, key=sort_key, reverse=reverse)


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "quant-monitor-python-backend",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health")
def health() -> dict[str, Any]:
    exists = reader.multi_period_path.exists()
    return {
        "status": "ok" if exists else "missing_report",
        "multiPeriodReportExists": exists,
        "multiPeriodReportPath": str(reader.multi_period_path),
    }


@app.get("/api/market/metadata")
def market_metadata() -> dict[str, Any]:
    try:
        return reader.metadata()
    except ReportNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/market/overview")
def market_overview() -> dict[str, Any]:
    try:
        return reader.overview()
    except ReportNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/market/symbols")
def market_symbols() -> dict[str, Any]:
    try:
        symbols = reader.symbols()
        return {"count": len(symbols), "symbols": symbols}
    except ReportNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/market/rows")
def market_rows(
    instrument: str | None = Query(default=None),
    bar: str | None = Query(default=None),
    gate: str | None = Query(default=None),
    dataStatus: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
    sort: Literal["instrument", "bar", "date", "periodWeight", "topWeatherScore"] = "instrument",
    order: Literal["asc", "desc"] = "asc",
) -> dict[str, Any]:
    try:
        rows = reader.rows(instrument=instrument, bar=bar, gate=gate, data_status=dataStatus)
    except ReportNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    rows = sort_rows(rows, sort=sort, order=order)
    return {
        "count": len(rows),
        "limit": limit,
        "filters": {
            "instrument": normalize_instrument(instrument),
            "bar": normalize_bar(bar),
            "gate": gate,
            "dataStatus": dataStatus,
        },
        "rows": rows[:limit],
    }


@app.get("/api/market/current/{instrument}")
def market_current(
    instrument: str,
    bar: str = Query(default="4H"),
) -> dict[str, Any]:
    try:
        row = reader.current(instrument=instrument, bar=bar)
    except ReportNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No current row for {normalize_instrument(instrument)} {normalize_bar(bar)}",
        )
    return {"instrument": normalize_instrument(instrument), "bar": normalize_bar(bar), "row": row}


@app.get("/api/scanner/status")
def scanner_status() -> dict[str, Any]:
    try:
        metadata = reader.metadata()
    except ReportNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {
        "mode": "reports_reader",
        "note": "Stage 1 migration reads existing reports; live scan execution remains in Node scripts.",
        "startedAt": metadata.get("startedAt"),
        "finishedAt": metadata.get("finishedAt"),
        "successCount": metadata.get("successCount"),
        "weatherCount": metadata.get("weatherCount"),
        "errorCount": metadata.get("errorCount"),
        "sourceReport": metadata.get("sourceReport"),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend_py.main:app", host="127.0.0.1", port=8000, reload=False)
