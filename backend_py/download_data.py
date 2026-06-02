from __future__ import annotations

import json
import sys

from backend_py.data_io import write_json
from backend_py.reports_reader import DATA_RAW_DIR
from backend_py.research.config import file_stem, parse_args
from backend_py.research.okx import download_okx_history


def main(argv: list[str] | None = None) -> None:
    config = parse_args(list(argv if argv is not None else sys.argv[1:]))
    output_path = DATA_RAW_DIR / f"{file_stem(config)}_raw.json"
    raw_payload = download_okx_history(config)
    write_json(output_path, raw_payload)
    print(
        json.dumps(
            {
                "step": "download-py",
                "outputPath": str(output_path),
                "instrument": raw_payload["instrument"],
                "bar": raw_payload["bar"],
                "rowCount": raw_payload["rowCount"],
                "pageCount": raw_payload["pageCount"],
                "downloadedAt": raw_payload["downloadedAt"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
