from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field


@dataclass
class IndicatorConfig:
    atrPeriod: int = 14
    fibAtrPeriods: list[int] = field(default_factory=lambda: [3, 8, 13, 21])
    volumeMaPeriod: int = 20
    middlePeriod: int = 21
    maPeriod: int = 233
    momentumPeriods: list[int] = field(default_factory=lambda: [8, 13, 21, 34])
    trendWeights: dict[str, float] = field(default_factory=lambda: {"8": 0.35, "13": 0.3, "21": 0.22, "34": 0.13})


@dataclass
class ThresholdConfig:
    strongTrendPct: float = 3
    weakTrendPct: float = 1.2
    volatilityBreakout: float = 1.2
    volumeExpansion: float = 1.5
    hotPct: float = 85
    coldPct: float = 15
    divergencePct: float = 1
    quietTrendPct: float = 1.2


@dataclass
class ResearchConfig:
    instrument: str = "BTC-USDT-SWAP"
    bar: str = "1D"
    days: int = 1200
    requestLimit: int = 100
    fromDate: str | None = None
    toDate: str | None = None
    indicator: IndicatorConfig = field(default_factory=IndicatorConfig)
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)
    horizons: list[int] = field(default_factory=lambda: [1, 3, 5, 10])


def default_config() -> ResearchConfig:
    return ResearchConfig()


def parse_args(argv: list[str], config: ResearchConfig | None = None) -> ResearchConfig:
    next_config = deepcopy(config or default_config())
    index = 0
    while index < len(argv):
        arg = argv[index]
        value = argv[index + 1] if index + 1 < len(argv) else None
        if arg == "--instrument" and value:
            next_config.instrument = value
            index += 2
        elif arg == "--bar" and value:
            next_config.bar = value
            index += 2
        elif arg == "--days" and value:
            next_config.days = int(value)
            index += 2
        elif arg == "--limit" and value:
            next_config.requestLimit = int(value)
            index += 2
        elif arg == "--from" and value:
            next_config.fromDate = value
            index += 2
        elif arg == "--to" and value:
            next_config.toDate = value
            index += 2
        else:
            index += 1
    return next_config


def file_stem(config: ResearchConfig) -> str:
    return f"{config.instrument.replace('-', '_')}_{config.bar}"


def report_stem(config: ResearchConfig) -> str:
    suffix = "_".join(part for part in [f"from_{config.fromDate}" if config.fromDate else "", f"to_{config.toDate}" if config.toDate else ""] if part)
    return f"{file_stem(config)}_{suffix}" if suffix else file_stem(config)

