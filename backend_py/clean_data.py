from __future__ import annotations

import json
import sys

from backend_py.data_io import read_json, write_csv, write_json
from backend_py.reports_reader import DATA_CLEAN_DIR, DATA_RAW_DIR
from backend_py.research.clean import candles_to_csv_rows, clean_okx_raw
from backend_py.research.config import file_stem, parse_args


def main(argv: list[str] | None = None) -> None:
    config = parse_args(list(argv if argv is not None else sys.argv[1:]))
    stem = file_stem(config)
    input_path = DATA_RAW_DIR / f"{stem}_raw.json"
    clean_json_path = DATA_CLEAN_DIR / f"{stem}_clean.json"
    clean_csv_path = DATA_CLEAN_DIR / f"{stem}_clean.csv"
    raw_payload = read_json(input_path)
    clean_payload = clean_okx_raw(raw_payload)
    write_json(clean_json_path, clean_payload)
    write_csv(clean_csv_path, candles_to_csv_rows(clean_payload["candles"]))
    print(
        json.dumps(
            {
                "step": "clean-py",
                "inputPath": str(input_path),
                "cleanJsonPath": str(clean_json_path),
                "cleanCsvPath": str(clean_csv_path),
                "metadata": clean_payload["metadata"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
