from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from backend_py.data_io import read_json, write_csv, write_json
from backend_py.reports_reader import DATA_CLEAN_DIR, PROJECT_ROOT
from backend_py.research.config import file_stem, parse_args
from backend_py.research.macro_data import (
    FRED_SOURCES,
    STABLECOIN_SOURCE,
    build_macro_feature_rows,
    macro_rows_to_csv_rows,
    parse_fred_csv,
    parse_stablecoin_chart,
    utc_now_iso,
)


DATA_MACRO_DIR = PROJECT_ROOT / "data" / "macro"
DATA_MACRO_RAW_DIR = DATA_MACRO_DIR / "raw"


def plan_outputs_enabled(args: list[str]) -> bool:
    return "--plan-outputs" in args


def fetch_text(url: str) -> str:
    request = Request(url, headers={"user-agent": "quant-monitor-terminal/0.1"})
    with urlopen(request, timeout=30) as response:  # noqa: S310 - URLs are fixed macro sources.
        return response.read().decode("utf-8")


def output_plan(paths: list[Path]) -> dict[str, Any]:
    return {
        "step": "download-macro-data-output-plan",
        "pathCount": len(paths),
        "existingCount": sum(1 for path in paths if path.exists()),
        "missingCount": sum(1 for path in paths if not path.exists()),
        "paths": [{"path": str(path), "exists": path.exists()} for path in paths],
    }


def download_fred_sources() -> dict[str, list[dict[str, Any]]]:
    DATA_MACRO_RAW_DIR.mkdir(parents=True, exist_ok=True)
    source_rows_by_key = {}
    for source in FRED_SOURCES:
        text = fetch_text(source["url"])
        (DATA_MACRO_RAW_DIR / f"{source['id']}.csv").write_text(text, encoding="utf-8")
        source_rows_by_key[source["key"]] = parse_fred_csv(text, source)
    return source_rows_by_key


def download_stablecoin_source() -> list[dict[str, Any]]:
    try:
        text = fetch_text(STABLECOIN_SOURCE["url"])
        (DATA_MACRO_RAW_DIR / "defillama_stablecoincharts_all.json").write_text(text, encoding="utf-8")
        return parse_stablecoin_chart(json.loads(text))
    except Exception as error:  # noqa: BLE001 - stablecoin source is optional, matching the Node path.
        print(f"stablecoin source skipped: {error}", file=sys.stderr)
        return []


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    config = parse_args(args)
    stem = file_stem(config)
    clean_path = DATA_CLEAN_DIR / f"{stem}_clean.json"
    macro_json_path = DATA_MACRO_DIR / f"{stem}_macro_features.json"
    macro_csv_path = DATA_MACRO_DIR / f"{stem}_macro_features.csv"
    raw_paths = [DATA_MACRO_RAW_DIR / f"{source['id']}.csv" for source in FRED_SOURCES]
    raw_paths.append(DATA_MACRO_RAW_DIR / "defillama_stablecoincharts_all.json")

    if plan_outputs_enabled(args):
        print(json.dumps(output_plan([macro_json_path, macro_csv_path, *raw_paths]), ensure_ascii=False, indent=2))
        return

    clean_payload = read_json(clean_path)
    source_rows_by_key = download_fred_sources()
    stablecoin_rows = download_stablecoin_source()
    if stablecoin_rows:
        source_rows_by_key[STABLECOIN_SOURCE["key"]] = stablecoin_rows

    candle_dates = [candle["date"] for candle in clean_payload["candles"]]
    macro_rows = build_macro_feature_rows(candle_dates, source_rows_by_key)
    write_json(
        macro_json_path,
        {
            "metadata": {
                "instrument": clean_payload["metadata"]["instrument"],
                "bar": clean_payload["metadata"]["bar"],
                "firstDate": macro_rows[0]["date"] if macro_rows else None,
                "lastDate": macro_rows[-1]["date"] if macro_rows else None,
                "rowCount": len(macro_rows),
                "sources": [
                    *[
                        {"key": source["key"], "id": source["id"], "label": source["label"], "url": source["url"]}
                        for source in FRED_SOURCES
                    ],
                    {
                        "key": STABLECOIN_SOURCE["key"],
                        "label": STABLECOIN_SOURCE["label"],
                        "url": STABLECOIN_SOURCE["url"],
                        "rows": len(stablecoin_rows),
                    },
                ],
                "generatedAt": utc_now_iso(),
            },
            "rows": macro_rows,
        },
    )
    write_csv(macro_csv_path, macro_rows_to_csv_rows(macro_rows))
    print(
        json.dumps(
            {
                "step": "download-macro-data-py",
                "cleanPath": str(clean_path),
                "rawDir": str(DATA_MACRO_RAW_DIR),
                "macroJsonPath": str(macro_json_path),
                "macroCsvPath": str(macro_csv_path),
                "rowCount": len(macro_rows),
                "stablecoinRows": len(stablecoin_rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
