from __future__ import annotations

import argparse
import bisect
import csv
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

from backend_py.build_summary import DEFAULT_SYMBOLS, split_csv_values
from backend_py.data_io import read_json, write_csv, write_json
from backend_py.reports_reader import DATA_CLEAN_DIR, REPORTS_DIR
from backend_py.research.config import ResearchConfig, file_stem
from backend_py.research.feature_factory import build_indicator_snapshots, build_weather_labels, route_strategies
from backend_py.research.summary import history_quality


DEFAULT_BARS = ["1D", "4H", "8H", "1W"]
DEFAULT_HORIZONS = [1, 3, 5, 10]
RANGE_QUANTILE = 50.0
CHAOS_QUANTILE = 75.0
MIN_OBSERVATIONS = 30
MAIN_HORIZONS = {5, 10}
CSV_ENCODING = "utf-8-sig"

HIT_MEANINGS = {
    "TREND": "方向命中",
    "RANGE": "低波动维持",
    "CHAOS": "高扰动命中",
}

OBSERVATION_FIELDS = [
    "instrument",
    "bar",
    "date",
    "year",
    "index",
    "horizon",
    "environment",
    "environmentDirection",
    "hitMeaning",
    "mappingReason",
    "periodWeight",
    "historyQuality",
    "dataStatus",
    "lowSampleSymbol",
    "close",
    "trendState",
    "volatilityState",
    "shortAtrState",
    "trendScore",
    "resonanceDirection",
    "resonanceCount",
    "atrPercentile",
    "volatilityMultiple",
    "volatilityMultiplePercentile",
    "atr3To21",
    "atr8To21",
    "trendFollowingScore",
    "breakoutScore",
    "meanReversionScore",
    "gridScore",
    "waitScore",
    "futureReturnPct",
    "absFutureReturnPct",
    "maxUpPct",
    "maxDownPct",
    "futureRangePct",
    "rangeThresholdPct",
    "chaosThresholdPct",
    "hit",
    "baselineRateAtT",
    "baselineSampleCount",
    "weight",
]

SUMMARY_FIELDS = [
    "instrument",
    "bar",
    "horizon",
    "environment",
    "environmentDirection",
    "hitMeaning",
    "observations",
    "weightedObservations",
    "hitRatePct",
    "baselineRatePct",
    "liftPct",
    "liftWilsonLow",
    "avgFutureReturnPct",
    "medianFutureReturnPct",
    "avgAbsFutureReturnPct",
    "avgFutureRangePct",
    "periodWeightAvg",
    "lowSample",
    "eligibleForCross",
    "mainHorizon",
    "passCandidate",
    "firstDate",
    "lastDate",
]

YEAR_SUMMARY_FIELDS = [
    "instrument",
    "bar",
    "year",
    "horizon",
    "environment",
    "environmentDirection",
    "hitMeaning",
    "observations",
    "hitRatePct",
    "baselineRatePct",
    "liftPct",
    "lowSample",
    "mainHorizon",
    "firstDate",
    "lastDate",
]

CROSS_FIELDS = [
    "bar",
    "horizon",
    "environment",
    "environmentDirection",
    "hitMeaning",
    "symbolCount",
    "observations",
    "weightedObservations",
    "weightedHitRatePct",
    "weightedBaselineRatePct",
    "weightedLiftPct",
    "liftWilsonLow",
    "lowSampleGroupsExcluded",
    "mainHorizon",
    "passCandidate",
]


def finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if finite(numerator) and finite(denominator) and denominator else 0.0


def round_value(value: Any, digits: int = 4) -> float | str:
    if not finite(value):
        return ""
    return round(float(value), digits)


def split_values(values: list[str] | None, default: list[str]) -> list[str]:
    return split_csv_values(values or []) or list(default)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Gate-1 A-layer causal environment effectiveness backtest.")
    parser.add_argument("--symbols", nargs="*", help="Symbols to evaluate. Defaults to production symbols.")
    parser.add_argument("--bars", nargs="*", default=[",".join(DEFAULT_BARS)], help="Bars to evaluate.")
    parser.add_argument("--horizons", nargs="*", default=[",".join(str(item) for item in DEFAULT_HORIZONS)], help="Horizon bars to evaluate.")
    parser.add_argument("--range-quantile", type=float, default=RANGE_QUANTILE)
    parser.add_argument("--chaos-quantile", type=float, default=CHAOS_QUANTILE)
    parser.add_argument("--min-observations", type=int, default=MIN_OBSERVATIONS)
    parser.add_argument("--output-prefix", default="gate1")
    parsed = parser.parse_args(argv)
    parsed.symbols = split_values(parsed.symbols, DEFAULT_SYMBOLS)
    parsed.bars = split_values(parsed.bars, DEFAULT_BARS)
    parsed.horizons = [int(item) for item in split_values(parsed.horizons, [str(item) for item in DEFAULT_HORIZONS])]
    return parsed


def clean_path_for(config: ResearchConfig) -> Path:
    path = DATA_CLEAN_DIR / f"{file_stem(config)}_clean.json"
    resolved_dir = DATA_CLEAN_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_path.parent != resolved_dir:
        raise ValueError(f"Unsafe clean path: {path}")
    return path


def csv_writer(path: Path, fieldnames: list[str]) -> tuple[Any, csv.DictWriter]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", encoding=CSV_ENCODING, newline="")
    writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    return handle, writer


def label_by_dimension(labels: list[dict[str, Any]], dimension: str) -> dict[str, Any]:
    return next((label for label in labels if label.get("dimension") == dimension), {})


def future_price_stats(candles: list[dict[str, Any]], index: int, horizon: int) -> dict[str, float] | None:
    if index < 0 or index >= len(candles):
        return None
    entry = candles[index]
    future = candles[index + 1 : index + 1 + horizon]
    if len(future) < horizon:
        return None
    exit_candle = future[-1]
    max_high = max(candle["high"] for candle in future)
    min_low = min(candle["low"] for candle in future)
    future_return = safe_divide(exit_candle["close"] - entry["close"], entry["close"]) * 100
    max_up = safe_divide(max_high - entry["close"], entry["close"]) * 100
    max_down = safe_divide(min_low - entry["close"], entry["close"]) * 100
    return {
        "futureReturnPct": future_return,
        "absFutureReturnPct": abs(future_return),
        "maxUpPct": max_up,
        "maxDownPct": max_down,
        "futureRangePct": max_up - max_down,
    }


def percentile_from_sorted(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * (quantile / 100)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] + ((values[upper] - values[lower]) * fraction)


def wilson_lower_bound(successes: int, observations: int, z: float = 1.96) -> float:
    if observations <= 0:
        return 0.0
    phat = successes / observations
    denom = 1 + (z * z / observations)
    center = phat + (z * z / (2 * observations))
    adjustment = z * math.sqrt(((phat * (1 - phat)) + (z * z / (4 * observations))) / observations)
    return max(0.0, (center - adjustment) / denom)


@dataclass
class CompletedHistory:
    returns: list[float] = field(default_factory=list)
    abs_returns: list[float] = field(default_factory=list)
    ranges: list[float] = field(default_factory=list)
    positive: int = 0
    negative: int = 0

    @property
    def count(self) -> int:
        return len(self.returns)

    def add(self, stats: dict[str, float]) -> None:
        future_return = stats["futureReturnPct"]
        self.returns.append(future_return)
        if future_return > 0:
            self.positive += 1
        if future_return < 0:
            self.negative += 1
        bisect.insort(self.abs_returns, abs(future_return))
        bisect.insort(self.ranges, stats["futureRangePct"])

    def range_threshold(self, quantile: float) -> float | None:
        return percentile_from_sorted(self.abs_returns, quantile)

    def chaos_threshold(self, quantile: float) -> float | None:
        return percentile_from_sorted(self.ranges, quantile)

    def trend_baseline(self, direction: str) -> float:
        wins = self.positive if direction == "up" else self.negative
        return safe_divide(wins, self.count) * 100

    def range_baseline(self, threshold: float) -> float:
        return safe_divide(bisect.bisect_right(self.abs_returns, threshold), self.count) * 100

    def chaos_baseline(self, threshold: float) -> float:
        return safe_divide(self.count - bisect.bisect_left(self.ranges, threshold), self.count) * 100


@dataclass
class MetricAccumulator:
    observations: int = 0
    hits: int = 0
    weighted_observations: float = 0.0
    weighted_hits: float = 0.0
    weighted_baseline_sum: float = 0.0
    baseline_sum: float = 0.0
    future_return_sum: float = 0.0
    abs_future_return_sum: float = 0.0
    future_range_sum: float = 0.0
    period_weight_sum: float = 0.0
    future_returns: list[float] = field(default_factory=list)
    symbols: set[str] = field(default_factory=set)
    first_date: str = ""
    last_date: str = ""

    def add(self, row: dict[str, Any]) -> None:
        hit = int(row["hit"])
        weight = float(row["weight"])
        baseline = float(row["baselineRateAtT"])
        future_return = float(row["futureReturnPct"])
        abs_return = float(row["absFutureReturnPct"])
        future_range = float(row["futureRangePct"])
        self.observations += 1
        self.hits += hit
        self.weighted_observations += weight
        self.weighted_hits += hit * weight
        self.weighted_baseline_sum += baseline * weight
        self.baseline_sum += baseline
        self.future_return_sum += future_return
        self.abs_future_return_sum += abs_return
        self.future_range_sum += future_range
        self.period_weight_sum += weight
        self.future_returns.append(future_return)
        self.symbols.add(str(row["instrument"]))
        date = str(row["date"])
        if not self.first_date or date < self.first_date:
            self.first_date = date
        if not self.last_date or date > self.last_date:
            self.last_date = date


def classify_environment(
    *,
    labels: list[dict[str, Any]],
    scores: dict[str, Any],
    snapshot: dict[str, Any],
) -> tuple[str, str, str, str]:
    trend = label_by_dimension(labels, "趋势")
    volatility = label_by_dimension(labels, "波动")
    short_atr = label_by_dimension(labels, "短波动")
    trend_state = str(trend.get("label") or "")
    volatility_state = str(volatility.get("label") or "")
    short_atr_state = str(short_atr.get("label") or "")
    trend_score = float(snapshot["momentum"]["trendScore"])
    abs_trend = abs(trend_score)
    resonance_direction = str(snapshot["momentum"]["resonanceDirection"])
    resonance_count = int(snapshot["momentum"]["resonanceCount"])
    trend_following = float(scores.get("trendFollowing") or 0)
    breakout = float(scores.get("breakout") or 0)
    mean_reversion = float(scores.get("meanReversion") or 0)
    grid = float(scores.get("grid") or 0)
    wait = float(scores.get("wait") or 0)
    top_active = max(trend_following, breakout, mean_reversion, grid)

    if trend_state == "强趋势上行" and resonance_direction == "up" and resonance_count >= 3 and trend_following >= 50 and trend_following >= max(breakout, mean_reversion, grid, wait):
        return ("TREND", "up", "强趋势上行 + trendFollowingScore>=50 + 趋势族最高", HIT_MEANINGS["TREND"])
    if trend_state == "强趋势下行" and resonance_direction == "down" and resonance_count >= 3 and trend_following >= 50 and trend_following >= max(breakout, mean_reversion, grid, wait):
        return ("TREND", "down", "强趋势下行 + trendFollowingScore>=50 + 趋势族最高", HIT_MEANINGS["TREND"])

    chaotic_volatility = (
        volatility_state == "高波动扩张"
        or float(snapshot["volatility"]["multiplePercentile"]) >= 70
        or float(snapshot["volatility"]["multiple"]) >= 1.5
        or short_atr_state == "短波动升温"
    )
    conflicting_trend = trend_state == "趋势不明" or resonance_direction == "mixed" or wait >= top_active
    if chaotic_volatility and conflicting_trend:
        return ("CHAOS", "neutral", "高波动/短波动升温 + 趋势不明/混合或 wait 最高", HIT_MEANINGS["CHAOS"])

    range_volatility = volatility_state in {"波动压缩", "常态波动", "高波动冷却"}
    quiet_structure = float(snapshot["volatility"]["atrPercentile"]) <= 40 or float(snapshot["volatility"]["multiple"]) <= 1.0
    if grid >= 50 and grid >= max(trend_following, breakout, mean_reversion) and abs_trend < 1.2 and quiet_structure and range_volatility:
        return ("RANGE", "neutral", "gridScore>=50 + grid 为最高主动族 + 低趋势 + 低/常态波动", HIT_MEANINGS["RANGE"])

    return ("OTHER", "neutral", "未进入 G1-A 主验收三态", "")


def rounded_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: round_value(value, 4) if isinstance(value, float) else value for key, value in row.items()}


def summary_row_from_accumulator(key: tuple[Any, ...], acc: MetricAccumulator, *, min_observations: int, include_instrument: bool = True) -> dict[str, Any]:
    if include_instrument:
        instrument, bar, horizon, environment, direction = key
    else:
        instrument = ""
        bar, horizon, environment, direction = key
    baseline = safe_divide(acc.baseline_sum, acc.observations)
    hit_rate = safe_divide(acc.hits, acc.observations) * 100
    weighted_hit_rate = safe_divide(acc.weighted_hits, acc.weighted_observations) * 100 if acc.weighted_observations else 0
    weighted_baseline = safe_divide(acc.weighted_baseline_sum, acc.weighted_observations) if acc.weighted_observations else baseline
    low_sample = acc.observations < min_observations
    lift = hit_rate - baseline
    wilson_lift = (wilson_lower_bound(acc.hits, acc.observations) * 100) - baseline
    row = {
        "instrument": instrument,
        "bar": bar,
        "horizon": horizon,
        "environment": environment,
        "environmentDirection": direction,
        "hitMeaning": HIT_MEANINGS.get(environment, ""),
        "observations": acc.observations,
        "weightedObservations": round_value(acc.weighted_observations, 4),
        "hitRatePct": round_value(hit_rate, 2),
        "baselineRatePct": round_value(baseline, 2),
        "liftPct": round_value(lift, 2),
        "liftWilsonLow": round_value(wilson_lift, 2),
        "avgFutureReturnPct": round_value(safe_divide(acc.future_return_sum, acc.observations), 4),
        "medianFutureReturnPct": round_value(percentile_from_sorted(sorted(acc.future_returns), 50) or 0, 4),
        "avgAbsFutureReturnPct": round_value(safe_divide(acc.abs_future_return_sum, acc.observations), 4),
        "avgFutureRangePct": round_value(safe_divide(acc.future_range_sum, acc.observations), 4),
        "periodWeightAvg": round_value(safe_divide(acc.period_weight_sum, acc.observations), 4),
        "lowSample": low_sample,
        "eligibleForCross": not low_sample,
        "mainHorizon": int(horizon) in MAIN_HORIZONS,
        "passCandidate": hit_rate >= 55 and lift > 0,
        "firstDate": acc.first_date,
        "lastDate": acc.last_date,
    }
    if not include_instrument:
        row["weightedHitRatePct"] = round_value(weighted_hit_rate, 2)
        row["weightedBaselineRatePct"] = round_value(weighted_baseline, 2)
        row["weightedLiftPct"] = round_value(weighted_hit_rate - weighted_baseline, 2)
        row["symbolCount"] = len(acc.symbols)
    return row


def year_summary_row(key: tuple[Any, ...], acc: MetricAccumulator, *, min_observations: int) -> dict[str, Any]:
    instrument, bar, year, horizon, environment, direction = key
    baseline = safe_divide(acc.baseline_sum, acc.observations)
    hit_rate = safe_divide(acc.hits, acc.observations) * 100
    lift = hit_rate - baseline
    return {
        "instrument": instrument,
        "bar": bar,
        "year": year,
        "horizon": horizon,
        "environment": environment,
        "environmentDirection": direction,
        "hitMeaning": HIT_MEANINGS.get(environment, ""),
        "observations": acc.observations,
        "hitRatePct": round_value(hit_rate, 2),
        "baselineRatePct": round_value(baseline, 2),
        "liftPct": round_value(lift, 2),
        "lowSample": acc.observations < min_observations,
        "mainHorizon": int(horizon) in MAIN_HORIZONS,
        "firstDate": acc.first_date,
        "lastDate": acc.last_date,
    }


def cross_row_from_accumulator(key: tuple[Any, ...], acc: MetricAccumulator, *, excluded: int) -> dict[str, Any]:
    if len(key) == 4:
        bar, horizon, environment, direction = key
    else:
        bar, horizon, environment = key
        direction = "all"
    weighted_hit_rate = safe_divide(acc.weighted_hits, acc.weighted_observations) * 100 if acc.weighted_observations else 0
    weighted_baseline = safe_divide(acc.weighted_baseline_sum, acc.weighted_observations) if acc.weighted_observations else 0
    return {
        "bar": bar,
        "horizon": horizon,
        "environment": environment,
        "environmentDirection": direction,
        "hitMeaning": HIT_MEANINGS.get(environment, ""),
        "symbolCount": len(acc.symbols),
        "observations": acc.observations,
        "weightedObservations": round_value(acc.weighted_observations, 4),
        "weightedHitRatePct": round_value(weighted_hit_rate, 2),
        "weightedBaselineRatePct": round_value(weighted_baseline, 2),
        "weightedLiftPct": round_value(weighted_hit_rate - weighted_baseline, 2),
        "liftWilsonLow": round_value((wilson_lower_bound(acc.hits, acc.observations) * 100) - weighted_baseline, 2),
        "lowSampleGroupsExcluded": excluded,
        "mainHorizon": int(horizon) in MAIN_HORIZONS,
        "passCandidate": weighted_hit_rate >= 55 and (weighted_hit_rate - weighted_baseline) > 0,
    }


def evaluate_symbol_bar(
    *,
    config: ResearchConfig,
    clean_payload: dict[str, Any],
    horizons: list[int],
    range_quantile: float,
    chaos_quantile: float,
    min_observations: int,
    observation_writer: csv.DictWriter,
    summary_accumulators: dict[tuple[Any, ...], MetricAccumulator],
    year_accumulators: dict[tuple[Any, ...], MetricAccumulator],
) -> dict[str, Any]:
    # Anti-lookahead invariant: baseline and percentile histories below are fed only by
    # outcomes whose ready_index is <= current snapshot.index. Router calibration and
    # lift artifacts are intentionally not read anywhere in this script.
    candles = clean_payload.get("candles") or []
    snapshots = build_indicator_snapshots(candles, config)
    quality = history_quality(config, (clean_payload.get("metadata") or {}).get("cleanRows") or 0, bool(snapshots), clean_payload.get("metadata") or {})
    period_weight = float(quality.get("periodWeight") or 0)
    histories = {horizon: CompletedHistory() for horizon in horizons}
    pending = {horizon: [] for horizon in horizons}
    pending_cursor = {horizon: 0 for horizon in horizons}
    rows_written = 0
    environment_counts: dict[str, int] = {}

    for snapshot in snapshots:
        current_index = int(snapshot["index"])
        for horizon in horizons:
            items = pending[horizon]
            cursor = pending_cursor[horizon]
            while cursor < len(items) and items[cursor][0] <= current_index:
                histories[horizon].add(items[cursor][1])
                cursor += 1
            pending_cursor[horizon] = cursor

        labels = build_weather_labels(snapshot, config)
        route_result = route_strategies(snapshot, labels)
        scores = route_result["scores"]
        environment, direction, reason, hit_meaning = classify_environment(labels=labels, scores=scores, snapshot=snapshot)

        for horizon in horizons:
            stats = future_price_stats(candles, current_index, horizon)
            if stats:
                pending[horizon].append((current_index + horizon, stats))
            if environment == "OTHER" or not stats:
                continue
            history = histories[horizon]
            if history.count <= 0:
                continue

            range_threshold = history.range_threshold(range_quantile)
            chaos_threshold = history.chaos_threshold(chaos_quantile)
            if environment == "TREND":
                hit = (stats["futureReturnPct"] > 0) if direction == "up" else (stats["futureReturnPct"] < 0)
                baseline = history.trend_baseline(direction)
            elif environment == "RANGE":
                if range_threshold is None:
                    continue
                hit = stats["absFutureReturnPct"] <= range_threshold
                baseline = history.range_baseline(range_threshold)
            elif environment == "CHAOS":
                if chaos_threshold is None:
                    continue
                hit = stats["futureRangePct"] >= chaos_threshold
                baseline = history.chaos_baseline(chaos_threshold)
            else:
                continue

            volatility = label_by_dimension(labels, "波动")
            short_atr = label_by_dimension(labels, "短波动")
            trend = label_by_dimension(labels, "趋势")
            row = rounded_row(
                {
                    "instrument": config.instrument,
                    "bar": config.bar,
                    "date": snapshot["date"],
                    "year": str(snapshot["date"])[:4],
                    "index": current_index,
                    "horizon": horizon,
                    "environment": environment,
                    "environmentDirection": direction,
                    "hitMeaning": hit_meaning,
                    "mappingReason": reason,
                    "periodWeight": period_weight,
                    "historyQuality": quality.get("historyQuality"),
                    "dataStatus": quality.get("dataStatus"),
                    "lowSampleSymbol": quality.get("historyQuality") == "insufficient",
                    "close": snapshot["price"]["last"],
                    "trendState": trend.get("label", ""),
                    "volatilityState": volatility.get("label", ""),
                    "shortAtrState": short_atr.get("label", ""),
                    "trendScore": snapshot["momentum"]["trendScore"],
                    "resonanceDirection": snapshot["momentum"]["resonanceDirection"],
                    "resonanceCount": snapshot["momentum"]["resonanceCount"],
                    "atrPercentile": snapshot["volatility"]["atrPercentile"],
                    "volatilityMultiple": snapshot["volatility"]["multiple"],
                    "volatilityMultiplePercentile": snapshot["volatility"]["multiplePercentile"],
                    "atr3To21": snapshot["volatility"]["fibAtrComparisons"]["atr3To21"],
                    "atr8To21": snapshot["volatility"]["fibAtrComparisons"]["atr8To21"],
                    "trendFollowingScore": scores.get("trendFollowing", 0),
                    "breakoutScore": scores.get("breakout", 0),
                    "meanReversionScore": scores.get("meanReversion", 0),
                    "gridScore": scores.get("grid", 0),
                    "waitScore": scores.get("wait", 0),
                    "futureReturnPct": stats["futureReturnPct"],
                    "absFutureReturnPct": stats["absFutureReturnPct"],
                    "maxUpPct": stats["maxUpPct"],
                    "maxDownPct": stats["maxDownPct"],
                    "futureRangePct": stats["futureRangePct"],
                    "rangeThresholdPct": range_threshold if range_threshold is not None else "",
                    "chaosThresholdPct": chaos_threshold if chaos_threshold is not None else "",
                    "hit": 1 if hit else 0,
                    "baselineRateAtT": baseline,
                    "baselineSampleCount": history.count,
                    "weight": period_weight,
                }
            )
            observation_writer.writerow(row)
            rows_written += 1
            environment_counts[environment] = environment_counts.get(environment, 0) + 1
            summary_key = (config.instrument, config.bar, horizon, environment, direction)
            summary_accumulators.setdefault(summary_key, MetricAccumulator()).add(row)
            year_key = (config.instrument, config.bar, row["year"], horizon, environment, direction)
            year_accumulators.setdefault(year_key, MetricAccumulator()).add(row)

    return {
        "instrument": config.instrument,
        "bar": config.bar,
        "cleanRows": (clean_payload.get("metadata") or {}).get("cleanRows"),
        "snapshotCount": len(snapshots),
        "dataStatus": quality.get("dataStatus"),
        "historyQuality": quality.get("historyQuality"),
        "periodWeight": period_weight,
        "observationRows": rows_written,
        "environmentCounts": environment_counts,
    }


def aggregate_cross(
    summary_accumulators: dict[tuple[Any, ...], MetricAccumulator],
    *,
    min_observations: int,
    by_direction: bool,
) -> list[dict[str, Any]]:
    accumulators: dict[tuple[Any, ...], MetricAccumulator] = {}
    excluded_counts: dict[tuple[Any, ...], int] = {}
    for source_key, source_acc in summary_accumulators.items():
        instrument, bar, horizon, environment, direction = source_key
        cross_key = (bar, horizon, environment, direction) if by_direction else (bar, horizon, environment)
        if source_acc.observations < min_observations:
            excluded_counts[cross_key] = excluded_counts.get(cross_key, 0) + 1
            continue
        acc = accumulators.setdefault(cross_key, MetricAccumulator())
        acc.observations += source_acc.observations
        acc.hits += source_acc.hits
        acc.weighted_observations += source_acc.weighted_observations
        acc.weighted_hits += source_acc.weighted_hits
        acc.weighted_baseline_sum += source_acc.weighted_baseline_sum
        acc.symbols.add(str(instrument))
    result = []
    for key, acc in accumulators.items():
        result.append(cross_row_from_accumulator(key, acc, excluded=excluded_counts.get(key, 0)))
    return sorted(result, key=lambda row: (row["bar"], int(row["horizon"]), row["environment"], row["environmentDirection"]))


def main(argv: list[str] | None = None) -> None:
    parsed = parse_args(argv)
    if parsed.range_quantile != RANGE_QUANTILE or parsed.chaos_quantile != CHAOS_QUANTILE:
        raise ValueError("G1-A口径已拍板: rangeQuantile=50, chaosQuantile=75")

    observation_path = REPORTS_DIR / f"{parsed.output_prefix}_observations.csv"
    summary_path = REPORTS_DIR / f"{parsed.output_prefix}_summary.csv"
    year_summary_path = REPORTS_DIR / f"{parsed.output_prefix}_year_summary.csv"
    cross_path = REPORTS_DIR / f"{parsed.output_prefix}_cross_symbol_summary.csv"
    environment_path = REPORTS_DIR / f"{parsed.output_prefix}_environment_summary.csv"
    coverage_path = REPORTS_DIR / f"{parsed.output_prefix}_coverage.csv"
    metadata_path = REPORTS_DIR / f"{parsed.output_prefix}_metadata.json"

    summary_accumulators: dict[tuple[Any, ...], MetricAccumulator] = {}
    year_accumulators: dict[tuple[Any, ...], MetricAccumulator] = {}
    coverage_rows: list[dict[str, Any]] = []
    started_at = datetime.now(timezone.utc)

    handle, writer = csv_writer(observation_path, OBSERVATION_FIELDS)
    try:
        for bar in parsed.bars:
            for symbol in parsed.symbols:
                config = ResearchConfig(instrument=symbol, bar=bar, days=3650)
                config.horizons = list(parsed.horizons)
                clean_path = clean_path_for(config)
                if not clean_path.exists():
                    coverage_rows.append({"instrument": symbol, "bar": bar, "status": "missing_clean", "path": str(clean_path)})
                    continue
                clean_payload = read_json(clean_path)
                coverage = evaluate_symbol_bar(
                    config=config,
                    clean_payload=clean_payload,
                    horizons=parsed.horizons,
                    range_quantile=parsed.range_quantile,
                    chaos_quantile=parsed.chaos_quantile,
                    min_observations=parsed.min_observations,
                    observation_writer=writer,
                    summary_accumulators=summary_accumulators,
                    year_accumulators=year_accumulators,
                )
                coverage_rows.append({"status": "ok", "path": str(clean_path), **coverage})
    finally:
        handle.close()

    summary_rows = [
        summary_row_from_accumulator(key, acc, min_observations=parsed.min_observations)
        for key, acc in summary_accumulators.items()
    ]
    summary_rows.sort(key=lambda row: (row["instrument"], row["bar"], int(row["horizon"]), row["environment"], row["environmentDirection"]))
    year_rows = [
        year_summary_row(key, acc, min_observations=parsed.min_observations)
        for key, acc in year_accumulators.items()
    ]
    year_rows.sort(key=lambda row: (row["instrument"], row["bar"], row["year"], int(row["horizon"]), row["environment"], row["environmentDirection"]))
    cross_rows = aggregate_cross(summary_accumulators, min_observations=parsed.min_observations, by_direction=True)
    environment_rows = aggregate_cross(summary_accumulators, min_observations=parsed.min_observations, by_direction=False)

    write_csv(summary_path, summary_rows)
    write_csv(year_summary_path, year_rows)
    write_csv(cross_path, cross_rows)
    write_csv(environment_path, environment_rows)
    write_csv(coverage_path, coverage_rows)

    metadata = {
        "step": "gate1-a-causal-environment-backtest",
        "startedAt": started_at.isoformat().replace("+00:00", "Z"),
        "finishedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "symbols": parsed.symbols,
        "bars": parsed.bars,
        "horizons": parsed.horizons,
        "rangeQuantile": parsed.range_quantile,
        "chaosQuantile": parsed.chaos_quantile,
        "minObservations": parsed.min_observations,
        "mainHorizons": sorted(MAIN_HORIZONS),
        "hitMeanings": HIT_MEANINGS,
        "antiLookahead": [
            "Reads only data/clean candles; no router calibration reports are read.",
            "Environment mapping uses only snapshot t labels and route scores.",
            "Future returns/ranges are used only for outcome evaluation.",
            "RANGE threshold uses only completed prior outcomes with j+h <= t.",
            "CHAOS threshold uses only completed prior outcomes with j+h <= t.",
            "baselineRateAtT uses only completed prior outcomes with j+h <= t.",
        ],
        "outputs": {
            "observationsCsv": str(observation_path),
            "summaryCsv": str(summary_path),
            "yearSummaryCsv": str(year_summary_path),
            "crossSymbolSummaryCsv": str(cross_path),
            "environmentSummaryCsv": str(environment_path),
            "coverageCsv": str(coverage_path),
            "metadataJson": str(metadata_path),
        },
        "rowCounts": {
            "coverage": len(coverage_rows),
            "summary": len(summary_rows),
            "yearSummary": len(year_rows),
            "crossSymbolSummary": len(cross_rows),
            "environmentSummary": len(environment_rows),
        },
        "note": "passCandidate is a reference flag only, not a Gate-1 pass/fail decision.",
    }
    write_json(metadata_path, metadata)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
