from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Callable

from backend_py.build_deviation_rules import main as build_deviation_rules
from backend_py.build_feature_factory import main as build_feature_factory
from backend_py.build_market_weather_router import main as build_market_weather_router
from backend_py.reports_reader import DATA_CLEAN_DIR, PROJECT_ROOT, REPORTS_DIR
from backend_py.research.config import file_stem, parse_args as parse_research_args, report_stem


FIXTURE_SYMBOLS = ["BTC-USDT", "SOL-USDT", "DOGE-USDT", "ENA-USDT"]
FIXTURE_BARS = ["1D", "4H", "8H"]
DAYS = 3650
REPORT_KINDS: tuple[tuple[str, Callable[[list[str] | None], None]], ...] = (
    ("feature_factory", build_feature_factory),
    ("deviation_rules", build_deviation_rules),
    ("market_weather_router", build_market_weather_router),
)
FIXTURE_CLEAN_DIR = PROJECT_ROOT / "tests" / "fixtures" / "data" / "clean"
GOLDEN_DIR = PROJECT_ROOT / "tests" / "golden"


def split_csv_values(values: list[str] | None) -> list[str]:
    return [item.strip() for value in values or [] for item in str(value).split(",") if item.strip()]


def parse_cli_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze compact Python golden parity fixtures.")
    parser.add_argument("--symbols", nargs="*", default=[",".join(FIXTURE_SYMBOLS)])
    parser.add_argument("--bars", nargs="*", default=[",".join(FIXTURE_BARS)])
    parser.add_argument("--days", type=int, default=DAYS)
    parsed = parser.parse_args(argv)
    parsed.symbols = split_csv_values(parsed.symbols) or FIXTURE_SYMBOLS
    parsed.bars = split_csv_values(parsed.bars) or FIXTURE_BARS
    return parsed


def remove_py_artifacts(report_name: str) -> int:
    removed = 0
    for extension in ("json", "csv"):
        for path in REPORTS_DIR.glob(f"{report_name}_*_py.{extension}"):
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def copy_json(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    payload = json.loads(source.read_text(encoding="utf-8"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parsed = parse_cli_args(list(argv if argv is not None else sys.argv[1:]))
    FIXTURE_CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    frozen_cells = 0
    frozen_reports = 0
    removed_temp_artifacts = 0

    for bar in parsed.bars:
        for symbol in parsed.symbols:
            config = parse_research_args(["--instrument", symbol, "--bar", bar, "--days", str(parsed.days)])
            stem = file_stem(config)
            report_name = report_stem(config)
            clean_source = DATA_CLEAN_DIR / f"{stem}_clean.json"
            if not clean_source.exists():
                raise FileNotFoundError(f"missing fixture input {clean_source}")
            shutil.copyfile(clean_source, FIXTURE_CLEAN_DIR / f"{stem}_clean.json")

            args = ["--instrument", symbol, "--bar", bar, "--days", str(parsed.days)]
            for kind, builder in REPORT_KINDS:
                builder(args)
                copy_json(REPORTS_DIR / f"{report_name}_{kind}_py.json", GOLDEN_DIR / f"{report_name}_{kind}.json")
                frozen_reports += 1

            removed_temp_artifacts += remove_py_artifacts(report_name)
            frozen_cells += 1

    print(
        json.dumps(
            {
                "step": "freeze-golden-fixtures",
                "symbols": parsed.symbols,
                "bars": parsed.bars,
                "days": parsed.days,
                "fixtureCleanDir": str(FIXTURE_CLEAN_DIR),
                "goldenDir": str(GOLDEN_DIR),
                "frozenCells": frozen_cells,
                "frozenReports": frozen_reports,
                "removedTempArtifacts": removed_temp_artifacts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
