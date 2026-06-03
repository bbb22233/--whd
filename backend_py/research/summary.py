from __future__ import annotations

import math
from typing import Any

from .config import ResearchConfig
from .feature_factory import js_sum


def finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def summary_round(value: Any, digits: int = 4) -> float | None:
    if not finite_number(value):
        return None
    return round(float(value), digits)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def aggregation_drop_ratio(metadata: dict[str, Any]) -> float:
    aggregation = metadata.get("aggregation") or {}
    total_buckets = float(aggregation.get("totalBuckets") or 0)
    if not finite_number(total_buckets) or total_buckets <= 0:
        return 0
    dropped_buckets = float(aggregation.get("droppedBuckets") or 0)
    if not finite_number(dropped_buckets) or dropped_buckets <= 0:
        return 0
    return clamp(dropped_buckets / total_buckets, 0, 1)


def history_quality_label(period_weight: float) -> str:
    if period_weight >= 1:
        return "full_weight"
    if period_weight >= 0.5:
        return "half_weight"
    return "weak_display_only"


def history_quality(config: ResearchConfig, clean_rows: Any, has_current: bool, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = metadata or {}
    warmup_bars = int(config.indicator.maPeriod or 0)
    rows = float(clean_rows or 0)
    effective_rows = max(0, rows - warmup_bars)
    aggregation_ratio = aggregation_drop_ratio(metadata)
    sample_weight = clamp(effective_rows / 500, 0, 1)
    truncation_factor = 0.7 if metadata.get("truncated") else 1
    aggregation_factor = clamp(1 - aggregation_ratio, 0, 1)

    if not has_current or rows < warmup_bars:
        return {
            "dataStatus": "insufficient_history",
            "historyQuality": "insufficient",
            "periodWeight": 0,
            "effectiveRows": effective_rows,
            "sampleWeight": 0,
            "truncationFactor": truncation_factor,
            "aggregationFactor": summary_round(aggregation_factor, 4),
            "aggregationDropRatio": summary_round(aggregation_ratio, 4),
            "truncated": bool(metadata.get("truncated")),
        }

    period_cap = 1
    if config.bar == "1W":
        if rows <= 300:
            period_cap = 0
        elif rows <= 364:
            period_cap = 0.5

    raw_weight = sample_weight * truncation_factor * aggregation_factor
    period_weight = summary_round(clamp(raw_weight, 0, period_cap), 2)
    return {
        "dataStatus": "ok",
        "historyQuality": history_quality_label(period_weight or 0),
        "periodWeight": period_weight,
        "effectiveRows": effective_rows,
        "sampleWeight": summary_round(sample_weight, 4),
        "truncationFactor": truncation_factor,
        "aggregationFactor": summary_round(aggregation_factor, 4),
        "aggregationDropRatio": summary_round(aggregation_ratio, 4),
        "truncated": bool(metadata.get("truncated")),
    }


def quality_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok_rows = [row for row in rows if row.get("dataStatus") == "ok"]
    weighted_weather_count = js_sum(float(row.get("periodWeight") or 0) for row in ok_rows)
    return {
        "weatherCount": len(ok_rows),
        "weightedWeatherCount": summary_round(weighted_weather_count, 2),
        "averagePeriodWeight": summary_round(weighted_weather_count / len(ok_rows), 4) if ok_rows else 0,
        "lowWeightCount": len([row for row in ok_rows if float(row.get("periodWeight") or 0) < 1]),
        "insufficientHistoryCount": len(rows) - len(ok_rows),
    }


def score_columns(strategy_scores: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {f"score_{row.get('key')}": row.get("score") for row in strategy_scores or []}


CURRENT_SUMMARY_KEYS = (
    "date",
    "close",
    "gate",
    "topWeatherRoute",
    "topWeatherScore",
    "weatherSummary",
    "actionBias",
    "volatilityState",
    "atrPct",
    "atrPercentile",
    "volatilityMultiple",
    "volatilityMultiplePercentile",
    "remainingMomentumAtr",
    "remainingMomentumState",
    "fiveDayAtrDownProbabilityPct",
    "fiveDayAtrUpProbabilityPct",
    "fiveDayFutureMomentumPositivePct",
    "atr3To21",
    "atr8To21",
    "middleState",
    "middleDeviationRate",
    "middleDeviationAtr",
    "middleTenDayReturnCloserPct",
    "maState",
    "maDeviationRate",
    "maDeviationAtr",
    "maTenDayContinueAwayPct",
    "trendState",
    "trendScore",
    "resonanceDirection",
    "resonanceCount",
    "volumeState",
    "volumeMultiple",
)


def build_summary_row(
    *,
    config: ResearchConfig,
    clean_payload: dict[str, Any],
    feature_result: dict[str, Any] | None,
    weather_result: dict[str, Any],
    deviation_rules: dict[str, Any] | None,
) -> dict[str, Any]:
    current = weather_result.get("current") or {}
    values = ((feature_result or {}).get("current") or {}).get("values") or {}
    final_weather = (deviation_rules or {}).get("finalWeather") or weather_result.get("deviationFinalWeather") or {}
    clean_meta = clean_payload.get("metadata") or {}
    quality = history_quality(config, clean_meta.get("cleanRows") or 0, bool(current.get("gate")), clean_meta)

    row = {
        "instrument": config.instrument,
        "bar": config.bar,
        "dataStatus": quality["dataStatus"],
        "historyQuality": quality["historyQuality"],
        "periodWeight": quality["periodWeight"],
        "effectiveRows": quality["effectiveRows"],
        "sampleWeight": quality["sampleWeight"],
        "truncationFactor": quality["truncationFactor"],
        "aggregationFactor": quality["aggregationFactor"],
        "aggregationDropRatio": quality["aggregationDropRatio"],
        "truncated": quality["truncated"],
        "truncationReason": clean_meta.get("truncationReason"),
        "requiredWarmupBars": config.indicator.maPeriod,
        "source": clean_meta.get("source"),
        "firstDate": clean_meta.get("firstDate"),
        "lastDate": clean_meta.get("lastDate"),
        "cleanRows": clean_meta.get("cleanRows"),
        "atr3Pct": summary_round(values.get("atr3Pct") if values.get("atr3Pct") is not None else current.get("atr3Pct")),
        "atr8Pct": summary_round(values.get("atr8Pct") if values.get("atr8Pct") is not None else current.get("atr8Pct")),
        "atr13Pct": summary_round(values.get("atr13Pct") if values.get("atr13Pct") is not None else current.get("atr13Pct")),
        "atr21Pct": summary_round(values.get("atr21Pct") if values.get("atr21Pct") is not None else current.get("atr21Pct")),
        "middlePositionPct": summary_round(values.get("middlePositionPct") if values.get("middlePositionPct") is not None else current.get("middlePositionPct")),
        "maPositionPct": summary_round(values.get("maPositionPct") if values.get("maPositionPct") is not None else current.get("maPositionPct")),
        "deviationWeather": final_weather.get("weather"),
    }
    if current:
        row.update({key: current.get(key) for key in CURRENT_SUMMARY_KEYS})
    if final_weather.get("riskNote") is not None:
        row["deviationRiskNote"] = final_weather.get("riskNote")
    row.update(score_columns(weather_result.get("strategyScores")))
    return row
