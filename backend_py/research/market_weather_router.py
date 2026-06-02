from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any

from .config import ResearchConfig
from .feature_factory import (
    build_indicator_snapshots,
    build_weather_labels,
    clamp,
    finite,
    js_round,
    route_strategies,
)
from .deviation_rules import build_deviation_rules, run_deviation_study_from_snapshots


def safe_divide(numerator: Any, denominator: Any) -> float:
    if not finite(numerator) or not finite(denominator) or denominator == 0:
        return 0
    return numerator / denominator


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0


def median(values: list[float]) -> float:
    if not values:
        return 0
    sorted_values = sorted(values)
    middle = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return sorted_values[middle]
    return (sorted_values[middle - 1] + sorted_values[middle]) / 2


def in_window(date: str, config: ResearchConfig) -> bool:
    if config.fromDate and date < config.fromDate:
        return False
    if config.toDate and date > config.toDate:
        return False
    return True


def confidence_label(samples: int, edge_percent: float) -> str:
    if samples < 120:
        return "样本偏少"
    if edge_percent >= 25:
        return "强"
    if edge_percent >= 15:
        return "中强"
    if edge_percent >= 8:
        return "中"
    return "弱"


def classify_volatility(snapshot: dict[str, Any]) -> dict[str, Any]:
    atr_percentile = snapshot["volatility"]["atrPercentile"]
    multiple_percentile = snapshot["volatility"]["multiplePercentile"]
    multiple = snapshot["volatility"]["multiple"]
    remaining = snapshot["volatility"]["remainingMomentumAtr"]
    candidates = [
        {"state": "波动压缩", "score": ((35 - atr_percentile) / 35) + ((35 - multiple_percentile) / 35)},
        {"state": "低波动启动", "score": ((45 - atr_percentile) / 45) + ((multiple_percentile - 70) / 30) + (0.25 if multiple >= 1 else 0)},
        {"state": "高波动扩张", "score": ((atr_percentile - 65) / 35) + ((multiple_percentile - 65) / 35) + (0.2 if remaining > 0 else 0)},
        {"state": "高波动冷却", "score": ((atr_percentile - 65) / 35) + ((35 - multiple_percentile) / 35) + (0.2 if remaining < 0 else 0)},
    ]
    candidates = [{**item, "score": max(0, item["score"])} for item in candidates]
    candidates.sort(key=lambda item: item["score"], reverse=True)
    if not candidates or candidates[0]["score"] <= 0.1:
        middle_distance = (abs(atr_percentile - 50) + abs(multiple_percentile - 50)) / 100
        return {"state": "常态波动", "confidencePct": js_round(clamp(1 - middle_distance, 0, 1) * 100, 2)}
    return {"state": candidates[0]["state"], "confidencePct": js_round(clamp(candidates[0]["score"] / 2, 0, 1) * 100, 2)}


def classify_short_atr(snapshot: dict[str, Any]) -> dict[str, Any]:
    atr3_to_21 = snapshot["volatility"]["fibAtrComparisons"]["atr3To21"]
    atr8_to_21 = snapshot["volatility"]["fibAtrComparisons"]["atr8To21"]
    if atr3_to_21 >= 1.08 and atr8_to_21 >= 1:
        return {"state": "短ATR升温", "confidencePct": js_round(clamp(((atr3_to_21 - 1) + max(0, atr8_to_21 - 1)) / 0.35, 0, 1) * 100, 2)}
    if atr3_to_21 <= 0.88 and atr8_to_21 <= 0.96:
        return {"state": "短ATR降温", "confidencePct": js_round(clamp(((1 - atr3_to_21) + max(0, 1 - atr8_to_21)) / 0.35, 0, 1) * 100, 2)}
    return {"state": "短ATR中性", "confidencePct": js_round(clamp(1 - abs(atr3_to_21 - 1), 0, 1) * 100, 2)}


def classify_energy(snapshot: dict[str, Any]) -> dict[str, Any]:
    remaining = snapshot["volatility"]["remainingMomentumAtr"]
    if remaining >= 0.2:
        return {"state": "振幅已超ATR", "confidencePct": js_round(clamp(remaining / 1.2, 0, 1) * 100, 2)}
    if remaining <= -0.2:
        return {"state": "振幅未满ATR", "confidencePct": js_round(clamp(abs(remaining) / 1.2, 0, 1) * 100, 2)}
    return {"state": "接近一倍ATR", "confidencePct": js_round(clamp(1 - abs(remaining) / 0.2, 0, 1) * 100, 2)}


def classify_trend(snapshot: dict[str, Any], config: ResearchConfig) -> dict[str, Any]:
    trend_score = snapshot["momentum"]["trendScore"]
    abs_trend = abs(trend_score)
    direction = snapshot["momentum"]["resonanceDirection"]
    count = snapshot["momentum"]["resonanceCount"]
    strong_trend_pct = config.thresholds.strongTrendPct or 3
    weak_trend_pct = config.thresholds.weakTrendPct or 1.2
    if count >= 3 and abs_trend >= strong_trend_pct and direction != "mixed":
        return {
            "state": "强趋势上行" if direction == "up" else "强趋势下行",
            "direction": direction,
            "strength": "strong",
            "confidencePct": js_round(clamp((abs_trend / (strong_trend_pct * 2)) + (count / 8), 0, 1) * 100, 2),
        }
    if count >= 2 and abs_trend >= weak_trend_pct:
        return {
            "state": "弱趋势上行" if direction == "up" else "弱趋势下行" if direction == "down" else "弱趋势混合",
            "direction": direction,
            "strength": "weak",
            "confidencePct": js_round(clamp((abs_trend / (strong_trend_pct * 2)) + (count / 10), 0, 0.75) * 100, 2),
        }
    return {"state": "趋势不明", "direction": "mixed", "strength": "none", "confidencePct": js_round(clamp(1 - (abs_trend / strong_trend_pct), 0, 1) * 100, 2)}


def classify_volume(snapshot: dict[str, Any], config: ResearchConfig) -> dict[str, Any]:
    multiple = snapshot["volume"]["multiple"]
    expansion = config.thresholds.volumeExpansion or 1.5
    if multiple >= expansion:
        return {"state": "放量", "confidencePct": js_round(clamp((multiple - expansion) / expansion, 0, 1) * 100, 2)}
    if multiple <= 0.75:
        return {"state": "缩量", "confidencePct": js_round(clamp((0.75 - multiple) / 0.75, 0, 1) * 100, 2)}
    return {"state": "量能正常", "confidencePct": js_round(clamp(1 - abs(multiple - 1), 0, 1) * 100, 2)}


def future_volatility_stats(snapshot: dict[str, Any], future_snapshot: dict[str, Any]) -> dict[str, Any]:
    atr_change_percent = safe_divide(future_snapshot["volatility"]["atrPct"] - snapshot["volatility"]["atrPct"], snapshot["volatility"]["atrPct"]) * 100
    multiple_change = future_snapshot["volatility"]["multiple"] - snapshot["volatility"]["multiple"]
    return {
        "atrChangePct": atr_change_percent,
        "atrDirection": "up" if atr_change_percent > 0 else "down" if atr_change_percent < 0 else "flat",
        "strongAtrUp": atr_change_percent >= 10,
        "strongAtrDown": atr_change_percent <= -10,
        "futureVolatilityMultiple": future_snapshot["volatility"]["multiple"],
        "futureRemainingMomentumAtr": future_snapshot["volatility"]["remainingMomentumAtr"],
        "futureRemainingMomentumPositive": future_snapshot["volatility"]["remainingMomentumAtr"] > 0,
        "multipleChange": multiple_change,
    }


def observation_rows(snapshots: list[dict[str, Any]], config: ResearchConfig) -> list[dict[str, Any]]:
    by_index = {snapshot["index"]: snapshot for snapshot in snapshots}
    selected = [snapshot for snapshot in snapshots if in_window(snapshot["date"], config)]
    rows = []
    for snapshot in selected:
        volatility = classify_volatility(snapshot)
        short_atr = classify_short_atr(snapshot)
        energy = classify_energy(snapshot)
        trend = classify_trend(snapshot, config)
        volume = classify_volume(snapshot, config)
        for horizon in config.horizons:
            future_snapshot = by_index.get(snapshot["index"] + horizon)
            if not future_snapshot:
                continue
            future = future_volatility_stats(snapshot, future_snapshot)
            rows.append(
                {
                    "date": snapshot["date"],
                    "horizon": horizon,
                    "volatilityState": volatility["state"],
                    "shortAtrState": short_atr["state"],
                    "energyState": energy["state"],
                    "trendState": trend["state"],
                    "volumeState": volume["state"],
                    "atrPct": js_round(snapshot["volatility"]["atrPct"]),
                    "atrPercentile": js_round(snapshot["volatility"]["atrPercentile"], 2),
                    "volatilityMultiple": js_round(snapshot["volatility"]["multiple"]),
                    "volatilityMultiplePercentile": js_round(snapshot["volatility"]["multiplePercentile"], 2),
                    "remainingMomentumAtr": js_round(snapshot["volatility"]["remainingMomentumAtr"]),
                    "atr3To21": js_round(snapshot["volatility"]["fibAtrComparisons"]["atr3To21"]),
                    "atr8To21": js_round(snapshot["volatility"]["fibAtrComparisons"]["atr8To21"]),
                    "volumeMultiple": js_round(snapshot["volume"]["multiple"]),
                    "trendScore": js_round(snapshot["momentum"]["trendScore"]),
                    "atrChangePct": js_round(future["atrChangePct"]),
                    "atrDirection": future["atrDirection"],
                    "strongAtrUp": 1 if future["strongAtrUp"] else 0,
                    "strongAtrDown": 1 if future["strongAtrDown"] else 0,
                    "futureVolatilityMultiple": js_round(future["futureVolatilityMultiple"]),
                    "futureRemainingMomentumAtr": js_round(future["futureRemainingMomentumAtr"]),
                    "futureRemainingMomentumPositive": 1 if future["futureRemainingMomentumPositive"] else 0,
                    "multipleChange": js_round(future["multipleChange"]),
                }
            )
    return rows


def summarize_component(rows: list[dict[str, Any]], component_key: str, component_label: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = f"{component_label}::{row[component_key]}::{row['horizon']}"
        groups.setdefault(key, []).append(row)

    result = []
    for group_rows in groups.values():
        first = group_rows[0]
        atr_changes = [row["atrChangePct"] for row in group_rows]
        up_pct = safe_divide(len([row for row in group_rows if row["atrDirection"] == "up"]), len(group_rows)) * 100
        down_pct = safe_divide(len([row for row in group_rows if row["atrDirection"] == "down"]), len(group_rows)) * 100
        edge = abs(up_pct - down_pct)
        result.append(
            {
                "component": component_label,
                "state": first[component_key],
                "horizon": first["horizon"],
                "occurrences": len(group_rows),
                "confidence": confidence_label(len(group_rows), edge),
                "probabilityEdgePct": js_round(edge, 2),
                "atrUpProbabilityPct": js_round(up_pct, 2),
                "atrDownProbabilityPct": js_round(down_pct, 2),
                "strongAtrUpProbabilityPct": js_round(safe_divide(len([row for row in group_rows if row["strongAtrUp"] == 1]), len(group_rows)) * 100, 2),
                "strongAtrDownProbabilityPct": js_round(safe_divide(len([row for row in group_rows if row["strongAtrDown"] == 1]), len(group_rows)) * 100, 2),
                "futureRemainingMomentumPositivePct": js_round(safe_divide(len([row for row in group_rows if row["futureRemainingMomentumPositive"] == 1]), len(group_rows)) * 100, 2),
                "avgAtrChangePct": js_round(average(atr_changes)),
                "medianAtrChangePct": js_round(median(atr_changes)),
                "avgFutureVolatilityMultiple": js_round(average([row["futureVolatilityMultiple"] for row in group_rows])),
                "medianFutureRemainingMomentumAtr": js_round(median([row["futureRemainingMomentumAtr"] for row in group_rows])),
                "lastSeen": group_rows[-1].get("date") or "",
            }
        )
    return result


def component_summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = [
        *summarize_component(rows, "volatilityState", "波动状态"),
        *summarize_component(rows, "shortAtrState", "短ATR状态"),
        *summarize_component(rows, "energyState", "波动超额状态"),
        *summarize_component(rows, "trendState", "趋势状态"),
        *summarize_component(rows, "volumeState", "量能状态"),
    ]
    component_order = {
        "波动超额状态": 0,
        "波动状态": 1,
        "短ATR状态": 2,
        "量能状态": 3,
        "趋势状态": 4,
    }
    state_order = {
        "接近一倍ATR": 0,
        "振幅未满ATR": 1,
        "振幅已超ATR": 2,
        "波动压缩": 0,
        "常态波动": 1,
        "低波动启动": 2,
        "高波动扩张": 3,
        "高波动冷却": 4,
        "短ATR降温": 0,
        "短ATR升温": 1,
        "短ATR中性": 2,
        "放量": 0,
        "量能正常": 1,
        "缩量": 2,
        "强趋势上行": 0,
        "强趋势下行": 1,
        "趋势不明": 2,
        "弱趋势混合": 3,
        "弱趋势上行": 4,
        "弱趋势下行": 5,
    }
    return sorted(result, key=lambda row: (component_order.get(row["component"], 99), state_order.get(row["state"], 99), row["horizon"]))


def current_component_rows(snapshot: dict[str, Any], summary_rows: list[dict[str, Any]], config: ResearchConfig) -> list[dict[str, Any]]:
    lookup = {f"{row['component']}::{row['state']}::{row['horizon']}": row for row in summary_rows}
    components = [
        {"component": "波动状态", **classify_volatility(snapshot)},
        {"component": "短ATR状态", **classify_short_atr(snapshot)},
        {"component": "波动超额状态", **classify_energy(snapshot)},
        {"component": "趋势状态", **classify_trend(snapshot, config)},
        {"component": "量能状态", **classify_volume(snapshot, config)},
    ]
    rows = []
    for component in components:
        for horizon in config.horizons:
            summary = lookup.get(f"{component['component']}::{component['state']}::{horizon}")
            rows.append(
                {
                    "date": snapshot["date"],
                    "close": js_round(snapshot["price"]["last"], 2),
                    "component": component["component"],
                    "state": component["state"],
                    "currentConfidencePct": component["confidencePct"],
                    "horizon": horizon,
                    "occurrences": summary.get("occurrences") if summary else 0,
                    "historicalConfidence": summary.get("confidence") if summary else "",
                    "probabilityEdgePct": summary.get("probabilityEdgePct") if summary else "",
                    "atrUpProbabilityPct": summary.get("atrUpProbabilityPct") if summary else "",
                    "atrDownProbabilityPct": summary.get("atrDownProbabilityPct") if summary else "",
                    "strongAtrUpProbabilityPct": summary.get("strongAtrUpProbabilityPct") if summary else "",
                    "strongAtrDownProbabilityPct": summary.get("strongAtrDownProbabilityPct") if summary else "",
                    "futureRemainingMomentumPositivePct": summary.get("futureRemainingMomentumPositivePct") if summary else "",
                    "avgAtrChangePct": summary.get("avgAtrChangePct") if summary else "",
                    "medianAtrChangePct": summary.get("medianAtrChangePct") if summary else "",
                    "avgFutureVolatilityMultiple": summary.get("avgFutureVolatilityMultiple") if summary else "",
                    "medianFutureRemainingMomentumAtr": summary.get("medianFutureRemainingMomentumAtr") if summary else "",
                }
            )
    return rows


def score_route_strategies(snapshot: dict[str, Any], config: ResearchConfig) -> dict[str, Any]:
    labels = build_weather_labels(snapshot, config)
    route_result = route_strategies(snapshot, labels)
    aggregate = route_result["scores"]
    scores = [
        {"key": "trendFollowing", "label": "趋势策略天气", "score": js_round(aggregate["trendFollowing"], 2)},
        {"key": "breakout", "label": "突破策略天气", "score": js_round(aggregate["breakout"], 2)},
        {"key": "meanReversion", "label": "均值回归天气", "score": js_round(aggregate["meanReversion"], 2)},
        {"key": "grid", "label": "网格震荡天气", "score": js_round(aggregate["grid"], 2)},
        {"key": "wait", "label": "防守等待", "score": js_round(aggregate["wait"], 2)},
    ]
    scores.sort(key=lambda row: row["score"], reverse=True)
    top_active_score = js_round(max(aggregate["trendFollowing"], aggregate["breakout"], aggregate["meanReversion"], aggregate["grid"]), 2)
    wait_score = js_round(aggregate["wait"], 2)
    return {
        "scores": scores,
        "topRoute": route_result["topRoutes"][0] if route_result["topRoutes"] else scores[0],
        "topActiveScore": top_active_score,
        "waitScore": wait_score,
        "routeResult": route_result,
    }


def score_bucket(score: float) -> str:
    if score >= 70:
        return "高适配"
    if score >= 50:
        return "中适配"
    if score >= 30:
        return "低适配"
    return "不适配"


def bucket_order(bucket: str) -> int:
    try:
        return ["不适配", "低适配", "中适配", "高适配"].index(bucket)
    except ValueError:
        return -1


def summarize_strategy_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = f"{row['routeKey']}::{row['scoreBucket']}::{row['horizon']}"
        groups.setdefault(key, []).append(row)

    summary_rows = []
    for group_rows in groups.values():
        first = group_rows[0]
        route_returns = [row["routeReturnPct"] for row in group_rows]
        directional_rows = [row for row in group_rows if row["directionalWin"] != ""]
        summary_rows.append(
            {
                "routeKey": first["routeKey"],
                "routeLabel": first["routeLabel"],
                "family": first["family"],
                "direction": first["direction"],
                "scoreBucket": first["scoreBucket"],
                "horizon": first["horizon"],
                "occurrences": len(group_rows),
                "avgScore": js_round(average([row["score"] for row in group_rows]), 2),
                "medianScore": js_round(median([row["score"] for row in group_rows]), 2),
                "successRatePct": js_round(safe_divide(len([row for row in group_rows if row["success"] == 1]), len(group_rows)) * 100, 2),
                "directionalWinRatePct": js_round(safe_divide(len([row for row in directional_rows if row["directionalWin"] == 1]), len(directional_rows)) * 100, 2) if directional_rows else "",
                "avgRouteReturnPct": js_round(average(route_returns)),
                "medianRouteReturnPct": js_round(median(route_returns)),
                "avgFutureReturnPct": js_round(average([row["futureReturnPct"] for row in group_rows])),
                "avgAbsReturnPct": js_round(average([row["absReturnPct"] for row in group_rows])),
                "avgMaxUpPct": js_round(average([row["maxUpPct"] for row in group_rows])),
                "avgMaxDownPct": js_round(average([row["maxDownPct"] for row in group_rows])),
                "lastSeen": group_rows[-1].get("date", ""),
            }
        )

    return sorted(summary_rows, key=lambda row: (row["routeKey"], row["horizon"], bucket_order(row["scoreBucket"])))


def future_price_stats(candles: list[dict[str, Any]], index: int, horizon: int) -> dict[str, Any] | None:
    entry = candles[index] if 0 <= index < len(candles) else None
    future = candles[index + 1 : index + 1 + horizon]
    if not entry or len(future) < horizon:
        return None
    exit_candle = future[-1]
    max_high = max(candle["high"] for candle in future)
    min_low = min(candle["low"] for candle in future)
    max_up_pct = safe_divide(max_high - entry["close"], entry["close"]) * 100
    max_down_pct = safe_divide(min_low - entry["close"], entry["close"]) * 100
    future_return_pct = safe_divide(exit_candle["close"] - entry["close"], entry["close"]) * 100
    return {
        "futureReturnPct": future_return_pct,
        "maxUpPct": max_up_pct,
        "maxDownPct": max_down_pct,
        "absReturnPct": abs(future_return_pct),
        "futureRangePct": max_up_pct - max_down_pct,
    }


def position_future_stats(snapshot: dict[str, Any], future_snapshot: dict[str, Any]) -> dict[str, Any]:
    current = snapshot["position"]["middleDeviationAtr"]
    future = future_snapshot["position"]["middleDeviationAtr"]
    current_abs = abs(current)
    future_abs = abs(future)
    side = 1 if current > 0 else -1 if current < 0 else 0
    return {
        "returnedCloser": future_abs < current_abs,
        "continuedAway": future_abs > current_abs,
        "crossedMiddle": side != 0 and future * side < 0,
        "distanceChangeAtr": future_abs - current_abs,
    }


def route_outcome(route: dict[str, Any], snapshot: dict[str, Any], future_snapshot: dict[str, Any], price_stats: dict[str, Any], horizon: int) -> dict[str, Any]:
    target_move_pct = max(snapshot["volatility"]["atrPct"], 0.5)
    position_stats = position_future_stats(snapshot, future_snapshot)
    allowed_grid_drift = target_move_pct * math.sqrt(max(1, horizon))
    allowed_grid_range = target_move_pct * 1.65 * math.sqrt(max(1, horizon))
    key = route["key"]
    if key == "trendLong":
        return {"success": price_stats["futureReturnPct"] > 0, "directionalWin": price_stats["futureReturnPct"] > 0, "routeReturnPct": price_stats["futureReturnPct"]}
    if key == "trendShort":
        return {"success": price_stats["futureReturnPct"] < 0, "directionalWin": price_stats["futureReturnPct"] < 0, "routeReturnPct": -price_stats["futureReturnPct"]}
    if key == "breakoutUp":
        return {"success": price_stats["maxUpPct"] >= target_move_pct, "directionalWin": price_stats["futureReturnPct"] > 0, "routeReturnPct": price_stats["maxUpPct"]}
    if key == "breakoutDown":
        return {"success": price_stats["maxDownPct"] <= -target_move_pct, "directionalWin": price_stats["futureReturnPct"] < 0, "routeReturnPct": abs(price_stats["maxDownPct"])}
    if key == "meanReversionLong":
        return {"success": snapshot["position"]["middleDeviationAtr"] < 0 and position_stats["returnedCloser"], "directionalWin": price_stats["futureReturnPct"] > 0, "routeReturnPct": price_stats["futureReturnPct"]}
    if key == "meanReversionShort":
        return {"success": snapshot["position"]["middleDeviationAtr"] > 0 and position_stats["returnedCloser"], "directionalWin": price_stats["futureReturnPct"] < 0, "routeReturnPct": -price_stats["futureReturnPct"]}
    if key == "gridNeutral":
        close_to_flat = abs(price_stats["futureReturnPct"]) <= allowed_grid_drift
        not_explosive = price_stats["futureRangePct"] <= allowed_grid_range
        return {"success": close_to_flat and not_explosive, "directionalWin": None, "routeReturnPct": -abs(price_stats["futureReturnPct"])}
    if key == "waitDefense":
        avoided_weak_long = price_stats["futureReturnPct"] <= 0 or price_stats["maxDownPct"] <= -target_move_pct
        return {"success": avoided_weak_long, "directionalWin": None, "routeReturnPct": max(0, -price_stats["futureReturnPct"])}
    return {"success": False, "directionalWin": None, "routeReturnPct": 0}


def strategy_observation_row(route: dict[str, Any], snapshot: dict[str, Any], labels: list[dict[str, Any]], price_stats: dict[str, Any], outcome: dict[str, Any], horizon: int) -> dict[str, Any]:
    return {
        "date": snapshot["date"],
        "routeKey": route["key"],
        "routeLabel": route["label"],
        "family": route["family"],
        "direction": route["direction"],
        "score": route["score"],
        "scoreBucket": score_bucket(route["score"]),
        "horizon": horizon,
        "close": js_round(snapshot["price"]["last"], 2),
        "weatherLabels": " | ".join(f"{label['dimension']}:{label['label']}" for label in labels),
        "reasons": " | ".join(route["reasons"]),
        "success": 1 if outcome["success"] else 0,
        "directionalWin": "" if outcome["directionalWin"] is None else 1 if outcome["directionalWin"] else 0,
        "routeReturnPct": js_round(outcome["routeReturnPct"]),
        "futureReturnPct": js_round(price_stats["futureReturnPct"]),
        "absReturnPct": js_round(price_stats["absReturnPct"]),
        "maxUpPct": js_round(price_stats["maxUpPct"]),
        "maxDownPct": js_round(price_stats["maxDownPct"]),
        "futureRangePct": js_round(price_stats["futureRangePct"]),
        "atrPct": js_round(snapshot["volatility"]["atrPct"]),
        "volatilityMultiple": js_round(snapshot["volatility"]["multiple"]),
        "atr3To21": js_round(snapshot["volatility"]["fibAtrComparisons"]["atr3To21"]),
        "volumeMultiple": js_round(snapshot["volume"]["multiple"]),
        "trendScore": js_round(snapshot["momentum"]["trendScore"]),
        "middleDeviationAtr": js_round(snapshot["position"]["middleDeviationAtr"]),
        "maDeviationAtr": js_round(snapshot["position"]["maDeviationAtr"]),
    }


def run_strategy_router_backtest(clean_payload: dict[str, Any], config: ResearchConfig, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [snapshot for snapshot in snapshots if in_window(snapshot["date"], config)]
    by_index = {snapshot["index"]: snapshot for snapshot in snapshots}
    rows = []
    current = None
    for snapshot in selected:
        labels = build_weather_labels(snapshot, config)
        route_result = route_strategies(snapshot, labels)
        current = {"date": snapshot["date"], "close": js_round(snapshot["price"]["last"], 2), "labels": labels, "scores": route_result["scores"], "topRoutes": route_result["topRoutes"]}
        for route in route_result["routes"]:
            for horizon in config.horizons:
                future_snapshot = by_index.get(snapshot["index"] + horizon)
                if not future_snapshot:
                    continue
                price_stats = future_price_stats(clean_payload["candles"], snapshot["index"], horizon)
                if not price_stats:
                    continue
                outcome = route_outcome(route, snapshot, future_snapshot, price_stats, horizon)
                rows.append(strategy_observation_row(route, snapshot, labels, price_stats, outcome, horizon))
    return {
        "metadata": {
            "instrument": clean_payload["metadata"]["instrument"],
            "bar": clean_payload["metadata"]["bar"],
            "fromDate": config.fromDate,
            "toDate": config.toDate,
            "firstDate": selected[0]["date"] if selected else None,
            "lastDate": selected[-1]["date"] if selected else None,
            "snapshotCount": len(selected),
            "routeCount": 8,
            "observationRows": len(rows),
            "horizons": config.horizons,
            "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "current": current,
        },
        "summaryRows": summarize_strategy_rows(rows),
        "observationRows": rows,
    }


def route_signal_type(route_key: str) -> str:
    if route_key.startswith("trend"):
        return "方向信号"
    if route_key.startswith("breakout"):
        return "波动方向信号"
    if route_key.startswith("meanReversion"):
        return "位置回归信号"
    if route_key == "gridNeutral":
        return "震荡状态信号"
    if route_key == "waitDefense":
        return "风险过滤信号"
    return "状态信号"


def traffic_light_name(score: float) -> str:
    if score >= 68:
        return "绿灯"
    if score >= 48:
        return "黄灯"
    return "红灯"


def light_reason(signal_type: str, stats: dict[str, Any]) -> str:
    if stats["occurrences"] < 30:
        return "样本偏少，只能观察"
    if signal_type == "方向信号" and stats["directionalWinRatePct"] < 50:
        return "方向胜率不足，不宜当进攻信号"
    if signal_type == "位置回归信号" and stats["successRatePct"] >= 55 and stats["avgRouteReturnPct"] <= 0.5:
        return "能证明位置回归，但不能证明直接开方向仓"
    if signal_type == "风险过滤信号":
        return "更适合做仓位/入场过滤，不是方向信号"
    if stats["successLiftPct"] > 5:
        return "当前分桶明显好于历史基线"
    if stats["successLiftPct"] > 0:
        return "当前分桶略好于历史基线"
    return "当前分桶没有明显优于历史基线"


def stats_for(rows: list[dict[str, Any]]) -> dict[str, Any]:
    directional_rows = [row for row in rows if row["directionalWin"] != ""]
    return {
        "occurrences": len(rows),
        "successRatePct": safe_divide(len([row for row in rows if row["success"] == 1]), len(rows)) * 100,
        "directionalWinRatePct": safe_divide(len([row for row in directional_rows if row["directionalWin"] == 1]), len(directional_rows)) * 100 if directional_rows else None,
        "avgRouteReturnPct": average([row["routeReturnPct"] for row in rows]),
        "avgFutureReturnPct": average([row["futureReturnPct"] for row in rows]),
        "avgAbsReturnPct": average([row["absReturnPct"] for row in rows]),
    }


def sample_confidence(occurrences: int) -> float:
    return clamp(math.sqrt(occurrences / 200) * 100, 0, 100)


def calibration_score(meta: dict[str, Any], current_score: float, bucket_stats: dict[str, Any], baseline_stats: dict[str, Any]) -> float:
    success_lift = bucket_stats["successRatePct"] - baseline_stats["successRatePct"]
    route_return_lift = bucket_stats["avgRouteReturnPct"] - baseline_stats["avgRouteReturnPct"]
    directional_lift = 0 if bucket_stats["directionalWinRatePct"] is None or baseline_stats["directionalWinRatePct"] is None else bucket_stats["directionalWinRatePct"] - baseline_stats["directionalWinRatePct"]
    sample = sample_confidence(bucket_stats["occurrences"])
    score = 42 + (current_score * 0.22) + (success_lift * 1.2) + clamp(route_return_lift * 3, -18, 18)
    if "方向" in meta["signalType"]:
        score += directional_lift * 0.9
    if meta["signalType"] == "位置回归信号" and bucket_stats["successRatePct"] >= 55 and bucket_stats["avgRouteReturnPct"] <= 0.5:
        score = min(score, 62)
    if meta["routeKey"] == "trendShort" and bucket_stats["directionalWinRatePct"] is not None and bucket_stats["directionalWinRatePct"] < 50:
        score = min(score, 46)
    if bucket_stats["occurrences"] < 30:
        score = min(score, 45)
    return clamp(score * (0.65 + (sample / 100 * 0.35)), 0, 100)


def light_rank(light: str) -> int:
    if light == "绿灯":
        return 3
    if light == "黄灯":
        return 2
    if light == "红灯":
        return 1
    return 0


def run_router_calibration(clean_payload: dict[str, Any], config: ResearchConfig, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    backtest = run_strategy_router_backtest(clean_payload, config, snapshots)
    rows = backtest["observationRows"]
    current_scores = (backtest["metadata"]["current"] or {}).get("scores", {})
    meta_by_route = {}
    for row in rows:
        meta_by_route.setdefault(
            row["routeKey"],
            {"routeKey": row["routeKey"], "routeLabel": row["routeLabel"], "family": row["family"], "direction": row["direction"], "signalType": route_signal_type(row["routeKey"])},
        )
    route_horizon_rows: dict[str, list[dict[str, Any]]] = {}
    route_horizon_bucket_rows: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        route_horizon_rows.setdefault(f"{row['routeKey']}::{row['horizon']}", []).append(row)
        route_horizon_bucket_rows.setdefault(f"{row['routeKey']}::{row['horizon']}::{row['scoreBucket']}", []).append(row)

    calibration_rows = []
    for route_key, meta in meta_by_route.items():
        current_score = current_scores.get(route_key, 0)
        current_bucket = score_bucket(current_score)
        for horizon in backtest["metadata"]["horizons"]:
            baseline = stats_for(route_horizon_rows.get(f"{route_key}::{horizon}", []))
            bucket = stats_for(route_horizon_bucket_rows.get(f"{route_key}::{horizon}::{current_bucket}", []))
            if not bucket["occurrences"] or not baseline["occurrences"]:
                continue
            success_lift_pct = bucket["successRatePct"] - baseline["successRatePct"]
            directional_lift_pct = None if bucket["directionalWinRatePct"] is None or baseline["directionalWinRatePct"] is None else bucket["directionalWinRatePct"] - baseline["directionalWinRatePct"]
            route_return_lift_pct = bucket["avgRouteReturnPct"] - baseline["avgRouteReturnPct"]
            confidence_pct = sample_confidence(bucket["occurrences"])
            score = calibration_score(meta, current_score, bucket, baseline)
            light = traffic_light_name(score)
            if current_bucket == "不适配":
                light = "红灯"
            if meta["signalType"] == "位置回归信号" and bucket["successRatePct"] >= 55 and bucket["avgRouteReturnPct"] <= 0.5 and light == "绿灯":
                light = "黄灯"
            if meta["routeKey"] == "trendShort" and bucket["directionalWinRatePct"] is not None and bucket["directionalWinRatePct"] < 50:
                light = "红灯"
            calibration_rows.append(
                {
                    "routeKey": route_key,
                    "routeLabel": meta["routeLabel"],
                    "family": meta["family"],
                    "direction": meta["direction"],
                    "signalType": meta["signalType"],
                    "horizon": horizon,
                    "currentScore": js_round(current_score, 2),
                    "currentBucket": current_bucket,
                    "light": light,
                    "calibrationScore": js_round(score, 2),
                    "sampleConfidencePct": js_round(confidence_pct, 2),
                    "occurrences": bucket["occurrences"],
                    "baselineOccurrences": baseline["occurrences"],
                    "successRatePct": js_round(bucket["successRatePct"], 2),
                    "baselineSuccessRatePct": js_round(baseline["successRatePct"], 2),
                    "successLiftPct": js_round(success_lift_pct, 2),
                    "directionalWinRatePct": "" if bucket["directionalWinRatePct"] is None else js_round(bucket["directionalWinRatePct"], 2),
                    "baselineDirectionalWinRatePct": "" if baseline["directionalWinRatePct"] is None else js_round(baseline["directionalWinRatePct"], 2),
                    "directionalLiftPct": "" if directional_lift_pct is None else js_round(directional_lift_pct, 2),
                    "avgRouteReturnPct": js_round(bucket["avgRouteReturnPct"], 2),
                    "baselineAvgRouteReturnPct": js_round(baseline["avgRouteReturnPct"], 2),
                    "routeReturnLiftPct": js_round(route_return_lift_pct, 2),
                    "avgFutureReturnPct": js_round(bucket["avgFutureReturnPct"], 2),
                    "avgAbsReturnPct": js_round(bucket["avgAbsReturnPct"], 2),
                    "reason": light_reason(meta["signalType"], {**bucket, "successLiftPct": success_lift_pct, "directionalLiftPct": directional_lift_pct, "routeReturnLiftPct": route_return_lift_pct}),
                }
            )
    calibration_rows.sort(key=lambda row: (-row["currentScore"], -row["calibrationScore"], row["horizon"]))
    signals = current_signals(calibration_rows, backtest)
    return {
        "metadata": {
            **backtest["metadata"],
            "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "calibration": {
                "scoreBuckets": "不适配:<30, 低适配:30-49, 中适配:50-69, 高适配:>=70",
                "sampleConfidence": "sqrt(当前分桶样本数 / 200)，最高100%",
                "lights": "绿灯=历史校准较强，黄灯=可观察/需确认，红灯=不适合单独开工",
            },
            "currentSignals": signals,
        },
        "calibrationRows": calibration_rows,
        "observationRows": backtest["observationRows"],
        "summaryRows": backtest["summaryRows"],
    }


def current_signals(calibration_rows: list[dict[str, Any]], backtest: dict[str, Any]) -> list[dict[str, Any]]:
    current_scores = (backtest["metadata"]["current"] or {}).get("scores", {})
    route_keys = [key for key in current_scores if key not in ["trendFollowing", "breakout", "meanReversion", "grid", "wait"]]
    best_rows = []
    for route_key in route_keys:
        rows = [row for row in calibration_rows if row["routeKey"] == route_key]
        if not rows:
            continue
        rows.sort(key=lambda row: (-light_rank(row["light"]), -row["calibrationScore"], -row["sampleConfidencePct"]))
        best_rows.append(rows[0])
    best_rows.sort(key=lambda row: -row["currentScore"])
    return [
        {
            "routeKey": row["routeKey"],
            "routeLabel": row["routeLabel"],
            "light": row["light"],
            "signalType": row["signalType"],
            "currentScore": row["currentScore"],
            "bestHorizon": row["horizon"],
            "calibrationScore": row["calibrationScore"],
            "sampleConfidencePct": row["sampleConfidencePct"],
            "successRatePct": row["successRatePct"],
            "successLiftPct": row["successLiftPct"],
            "directionalWinRatePct": row["directionalWinRatePct"],
            "avgRouteReturnPct": row["avgRouteReturnPct"],
            "reason": row["reason"],
        }
        for row in best_rows
    ]


LIGHT_GREEN = "绿灯"
LIGHT_YELLOW = "黄灯"
LIGHT_RED = "红灯"
GATE_GREEN = "绿"
GATE_YELLOW_GREEN = "黄偏绿"
GATE_YELLOW = "黄"
GATE_YELLOW_RED = "黄偏红"
GATE_RED = "红"
MIN_CALIBRATION_OCCURRENCES = 30
MIN_CALIBRATION_CONFIDENCE_PCT = 40
CONFIDENCE_GATE_PASS = "样本通过"
CONFIDENCE_GATE_WEAK = "样本不足"


def route_family_from_key(route_key: str = "") -> str:
    if route_key.startswith("trend"):
        return "trend"
    if route_key.startswith("breakout"):
        return "breakout"
    if route_key.startswith("meanReversion"):
        return "meanReversion"
    if route_key == "gridNeutral":
        return "grid"
    if route_key == "waitDefense":
        return "wait"
    return ""


def route_direction_from_key(route_key: str = "") -> str:
    if route_key.endswith("Long") or route_key.endswith("Up"):
        return "long"
    if route_key.endswith("Short") or route_key.endswith("Down"):
        return "short"
    return "neutral"


def numeric(value: Any) -> float:
    return float(value) if finite(value) else 0


def calibration_row_key(route_key: str | None, horizon: Any) -> str:
    return f"{route_key}::{horizon}"


def apply_confidence_gate_to_signals(signals: list[dict[str, Any]], calibration_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = {calibration_row_key(row["routeKey"], row["horizon"]): row for row in calibration_rows}
    result = []
    for signal in signals or []:
        direct_occurrences = signal.get("occurrences")
        occurrences = int(direct_occurrences) if finite(direct_occurrences) else int(numeric((lookup.get(calibration_row_key(signal.get("routeKey"), signal.get("bestHorizon"))) or {}).get("occurrences")))
        sample_confidence_pct = numeric(signal.get("sampleConfidencePct"))
        weak_sample = occurrences < MIN_CALIBRATION_OCCURRENCES or sample_confidence_pct < MIN_CALIBRATION_CONFIDENCE_PCT
        raw_light = signal.get("light")
        light = LIGHT_YELLOW if weak_sample and raw_light == LIGHT_GREEN else raw_light
        if occurrences < MIN_CALIBRATION_OCCURRENCES and sample_confidence_pct < MIN_CALIBRATION_CONFIDENCE_PCT:
            reason = f"occurrences {occurrences} < {MIN_CALIBRATION_OCCURRENCES}, sampleConfidencePct {js_round(sample_confidence_pct, 2)} < {MIN_CALIBRATION_CONFIDENCE_PCT}"
        elif occurrences < MIN_CALIBRATION_OCCURRENCES:
            reason = f"occurrences {occurrences} < {MIN_CALIBRATION_OCCURRENCES}"
        elif sample_confidence_pct < MIN_CALIBRATION_CONFIDENCE_PCT:
            reason = f"sampleConfidencePct {js_round(sample_confidence_pct, 2)} < {MIN_CALIBRATION_CONFIDENCE_PCT}"
        else:
            reason = ""
        result.append(
            {
                **signal,
                "occurrences": occurrences,
                "rawLight": raw_light,
                "light": light,
                "confidenceGate": CONFIDENCE_GATE_WEAK if weak_sample else CONFIDENCE_GATE_PASS,
                "confidenceGateReason": reason,
            }
        )
    return result


def compare_signal_key(signal: dict[str, Any]) -> tuple[int, float, float]:
    return (-light_rank(signal.get("light", "")), -numeric(signal.get("calibrationScore")), -numeric(signal.get("currentScore")))


def best_calibrated_signal(signals: list[dict[str, Any]]) -> dict[str, Any] | None:
    return sorted(signals, key=compare_signal_key)[0] if signals else None


def route_from_signal(signal: dict[str, Any], strategy_scores: dict[str, Any]) -> dict[str, Any]:
    raw_route = next((route for route in strategy_scores.get("routeResult", {}).get("routes", []) if route["key"] == signal["routeKey"]), None)
    return {
        **(raw_route or {}),
        "key": signal["routeKey"],
        "label": signal.get("routeLabel") or (raw_route or {}).get("label") or signal["routeKey"],
        "family": (raw_route or {}).get("family") or route_family_from_key(signal["routeKey"]),
        "direction": (raw_route or {}).get("direction") or route_direction_from_key(signal["routeKey"]),
        "score": js_round(numeric(signal.get("currentScore") or (raw_route or {}).get("score")), 2),
        "light": signal.get("light"),
        "rawLight": signal.get("rawLight") or signal.get("light"),
        "calibrationScore": signal.get("calibrationScore"),
        "bestHorizon": signal.get("bestHorizon"),
        "sampleConfidencePct": signal.get("sampleConfidencePct"),
        "occurrences": signal.get("occurrences"),
        "confidenceGate": signal.get("confidenceGate"),
        "confidenceGateReason": signal.get("confidenceGateReason"),
    }


def apply_calibration_to_strategy_scores(strategy_scores: dict[str, Any], signals: list[dict[str, Any]]) -> dict[str, Any]:
    top_signal = best_calibrated_signal(signals)
    if not top_signal:
        return {**strategy_scores, "calibratedTopSignal": None}
    return {**strategy_scores, "topRoute": route_from_signal(top_signal, strategy_scores), "calibratedTopSignal": top_signal}


def find_component(component_rows: list[dict[str, Any]], component: str, horizon: int) -> dict[str, Any] | None:
    return next((row for row in component_rows if row["component"] == component and row["horizon"] == horizon), None)


def gate_from_scores(strategy_scores: dict[str, Any], deviation_final: dict[str, Any], snapshot: dict[str, Any], component_rows: list[dict[str, Any]]) -> str:
    top_active = strategy_scores["topActiveScore"]
    wait = strategy_scores["waitScore"]
    energy5 = find_component(component_rows, "波动超额状态", 5)
    vol5 = find_component(component_rows, "波动状态", 5)
    big_weak = "大周期弱势" in (deviation_final.get("weather") or "")
    energy_low = (energy5 or {}).get("state") == "振幅未满ATR"
    compressed = (vol5 or {}).get("state") == "波动压缩"
    if big_weak and energy_low and top_active < 65:
        return "黄偏红"
    if wait >= 70 and top_active < 60:
        return "红"
    if wait >= 60 and top_active < 65:
        return "黄偏红"
    if top_active >= 75 and wait < 50:
        return "绿"
    if top_active >= 65 and wait < 60:
        return "黄偏绿"
    if compressed and top_active < 60:
        return "黄"
    if snapshot["volatility"]["atrPercentile"] <= 15 and energy_low:
        return "黄偏红"
    return "黄"


def gate_from_calibration(signals: list[dict[str, Any]], strategy_scores: dict[str, Any], deviation_final: dict[str, Any], snapshot: dict[str, Any], component_rows: list[dict[str, Any]]) -> str:
    if not signals:
        return gate_from_scores(strategy_scores, deviation_final, snapshot, component_rows)
    wait_signal = next((signal for signal in signals if route_family_from_key(signal.get("routeKey", "")) == "wait"), None)
    active_signals = [signal for signal in signals if route_family_from_key(signal.get("routeKey", "")) != "wait"]
    best_active = best_calibrated_signal(active_signals)
    green_active = [signal for signal in active_signals if signal.get("light") == LIGHT_GREEN]
    yellow_active = [signal for signal in active_signals if signal.get("light") == LIGHT_YELLOW]
    red_active = [signal for signal in active_signals if signal.get("light") == LIGHT_RED]
    active_count = len(active_signals)
    all_active_red = active_count > 0 and len(red_active) >= max(1, active_count - 1)
    wait_green = (wait_signal or {}).get("light") == LIGHT_GREEN
    wait_yellow_strong = (wait_signal or {}).get("light") == LIGHT_YELLOW and numeric((wait_signal or {}).get("currentScore")) >= 65 and numeric((wait_signal or {}).get("calibrationScore")) >= 55
    defensive_deviation = deviation_final.get("gate") in [GATE_RED, GATE_YELLOW_RED]
    if not best_active and wait_signal:
        if wait_green:
            return GATE_RED
        if wait_signal.get("light") == LIGHT_YELLOW:
            return GATE_YELLOW_RED
        return GATE_YELLOW
    if wait_green and not green_active:
        return GATE_RED if all_active_red else GATE_YELLOW_RED
    if all_active_red:
        return GATE_RED if wait_yellow_strong else GATE_YELLOW_RED
    if green_active:
        if defensive_deviation or wait_green or wait_yellow_strong or len(red_active) >= 3:
            return GATE_YELLOW_GREEN
        return GATE_GREEN
    if yellow_active:
        if defensive_deviation:
            return GATE_YELLOW_RED
        if wait_yellow_strong and numeric(wait_signal.get("currentScore")) >= numeric((best_active or {}).get("currentScore")):
            return GATE_YELLOW
        if numeric((best_active or {}).get("calibrationScore")) >= 58 and len(red_active) <= 3:
            return GATE_YELLOW_GREEN
        return GATE_YELLOW
    if wait_yellow_strong:
        return GATE_YELLOW_RED
    return GATE_YELLOW


def action_bias(gate: str, strategy_scores: dict[str, Any], deviation_final: dict[str, Any], component_rows: list[dict[str, Any]]) -> str:
    top = strategy_scores.get("topRoute") or {}
    top_key = top.get("key") or ""
    top_family = top.get("family") or top_key
    energy5 = find_component(component_rows, "波动超额状态", 5)
    vol5 = find_component(component_rows, "波动状态", 5)
    if gate == "红":
        return "防守等待，策略环境不友好"
    if gate == "黄偏红":
        return "谨慎观察，不把单一短期偏离当入场理由"
    if top_family == "wait" or top_key == "waitDefense":
        return "等待更清楚的波动或位置共振"
    if top_family == "breakout" and (vol5 or {}).get("state") == "波动压缩":
        return "突破预备天气，等待放量和方向确认"
    if top_family == "meanReversion":
        return "均值回归可观察，但要服从大周期过滤"
    if top_family == "grid":
        return "震荡/网格天气较友好，仍需控制突破风险"
    if top_family == "trend":
        return "趋势天气较友好，等方向和量能确认"
    if (energy5 or {}).get("state") == "振幅未满ATR":
        return "当根振幅未满ATR，避免追单"
    return deviation_final.get("actionBias") or "观察"


def find_current_rule(rules: list[dict[str, Any]], kind_key: str, horizon: int) -> dict[str, Any] | None:
    return next((row for row in rules if row["kindKey"] == kind_key and row["horizon"] == horizon), None)


def current_snapshot_row(snapshot: dict[str, Any], deviation_rules: dict[str, Any], component_rows: list[dict[str, Any]], strategy_scores: dict[str, Any], gate: str) -> dict[str, Any]:
    middle10 = find_current_rule(deviation_rules["currentRuleRows"], "middle", 10)
    ma10 = find_current_rule(deviation_rules["currentRuleRows"], "ma233", 10)
    volatility5 = find_component(component_rows, "波动状态", 5)
    short_atr5 = find_component(component_rows, "短ATR状态", 5)
    energy5 = find_component(component_rows, "波动超额状态", 5)
    trend = classify_trend(snapshot, ResearchConfig())
    volume = classify_volume(snapshot, ResearchConfig())
    calibrated = strategy_scores.get("calibratedTopSignal") or {}
    return {
        "date": snapshot["date"],
        "close": js_round(snapshot["price"]["last"], 2),
        "gate": gate,
        "topWeatherRoute": strategy_scores["topRoute"]["label"],
        "topWeatherScore": strategy_scores["topRoute"]["score"],
        "topWeatherLight": calibrated.get("light") or "",
        "topWeatherRawLight": calibrated.get("rawLight") or calibrated.get("light") or "",
        "topWeatherCalibrationScore": calibrated.get("calibrationScore") if calibrated else "",
        "topWeatherBestHorizon": calibrated.get("bestHorizon") if calibrated else "",
        "topWeatherOccurrences": calibrated.get("occurrences") if calibrated else "",
        "topWeatherSampleConfidencePct": calibrated.get("sampleConfidencePct") if calibrated else "",
        "topWeatherConfidenceGate": calibrated.get("confidenceGate") or "",
        "actionBias": action_bias(gate, strategy_scores, deviation_rules["finalWeather"], component_rows),
        "volatilityState": (volatility5 or {}).get("state", ""),
        "atrPct": js_round(snapshot["volatility"]["atrPct"]),
        "atrPercentile": js_round(snapshot["volatility"]["atrPercentile"], 2),
        "volatilityMultiple": js_round(snapshot["volatility"]["multiple"]),
        "volatilityMultiplePercentile": js_round(snapshot["volatility"]["multiplePercentile"], 2),
        "remainingMomentumAtr": js_round(snapshot["volatility"]["remainingMomentumAtr"]),
        "remainingMomentumState": (energy5 or {}).get("state", ""),
        "shortAtrState": (short_atr5 or {}).get("state", ""),
        "atr3Pct": js_round(snapshot["volatility"]["fibAtr"].get("3", {}).get("atrPct")),
        "atr8Pct": js_round(snapshot["volatility"]["fibAtr"].get("8", {}).get("atrPct")),
        "atr13Pct": js_round(snapshot["volatility"]["fibAtr"].get("13", {}).get("atrPct")),
        "atr21Pct": js_round(snapshot["volatility"]["fibAtr"].get("21", {}).get("atrPct")),
        "atr3To21": js_round(snapshot["volatility"]["fibAtrComparisons"]["atr3To21"]),
        "atr8To21": js_round(snapshot["volatility"]["fibAtrComparisons"]["atr8To21"]),
        "fiveDayAtrDownProbabilityPct": (volatility5 or {}).get("atrDownProbabilityPct", ""),
        "fiveDayAtrUpProbabilityPct": (volatility5 or {}).get("atrUpProbabilityPct", ""),
        "fiveDayFutureMomentumPositivePct": (energy5 or {}).get("futureRemainingMomentumPositivePct", ""),
        "middleState": (middle10 or {}).get("state", ""),
        "middleDeviationRate": (middle10 or {}).get("deviationRate", ""),
        "middleDeviationAtr": (middle10 or {}).get("deviationAtr", ""),
        "middlePositionPct": js_round(snapshot["position"]["middlePositionPct"], 2),
        "middleTenDayReturnCloserPct": (middle10 or {}).get("returnCloserProbabilityPct", ""),
        "maState": (ma10 or {}).get("state", ""),
        "maDeviationRate": (ma10 or {}).get("deviationRate", ""),
        "maDeviationAtr": (ma10 or {}).get("deviationAtr", ""),
        "maPositionPct": js_round(snapshot["position"]["maPositionPct"], 2),
        "maTenDayContinueAwayPct": (ma10 or {}).get("continueAwayProbabilityPct", ""),
        "trendState": trend["state"],
        "trendScore": js_round(snapshot["momentum"]["trendScore"]),
        "resonanceDirection": snapshot["momentum"]["resonanceDirection"],
        "resonanceCount": snapshot["momentum"]["resonanceCount"],
        "volumeState": volume["state"],
        "volumeMultiple": js_round(snapshot["volume"]["multiple"]),
        "weatherSummary": f"{(volatility5 or {}).get('state') or '未知波动'} / {(energy5 or {}).get('state') or '未知动能'} / {(middle10 or {}).get('weatherTag') or ''} / {(ma10 or {}).get('weatherTag') or ''}",
    }


def build_market_weather_router_components(clean_payload: dict[str, Any], config: ResearchConfig) -> dict[str, Any]:
    snapshots = build_indicator_snapshots(clean_payload["candles"], config)
    selected = [snapshot for snapshot in snapshots if in_window(snapshot["date"], config)]
    latest = selected[-1] if selected else None
    volatility_observation_rows = observation_rows(snapshots, config)
    summary_rows = component_summary_rows(volatility_observation_rows)
    deviation_study = run_deviation_study_from_snapshots(clean_payload, config, snapshots)
    deviation_rules = build_deviation_rules(deviation_study)
    component_rows = current_component_rows(latest, summary_rows, config) if latest else []
    calibration = run_router_calibration(clean_payload, config, snapshots) if latest else None
    calibration_signals = apply_confidence_gate_to_signals((calibration or {}).get("metadata", {}).get("currentSignals", []), (calibration or {}).get("calibrationRows", []))
    raw_strategy_scores = score_route_strategies(latest, config) if latest else {"scores": [], "topActiveScore": 0, "waitScore": 0, "topRoute": None}
    strategy_scores = apply_calibration_to_strategy_scores(raw_strategy_scores, calibration_signals) if latest else raw_strategy_scores
    gate = gate_from_calibration(calibration_signals, strategy_scores, deviation_rules["finalWeather"], latest, component_rows) if latest else "数据不足"
    current = current_snapshot_row(latest, deviation_rules, component_rows, strategy_scores, gate) if latest else None
    return {
        "metadata": {
            "instrument": clean_payload["metadata"]["instrument"],
            "bar": clean_payload["metadata"]["bar"],
            "fromDate": config.fromDate,
            "toDate": config.toDate,
            "firstDate": selected[0]["date"] if selected else None,
            "lastDate": latest["date"] if latest else None,
            "snapshotCount": len(selected),
            "observationRows": len(volatility_observation_rows),
            "routerCalibrationRows": len((calibration or {}).get("calibrationRows", [])),
            "routerCalibrationObservationRows": (calibration or {}).get("metadata", {}).get("observationRows", 0),
            "gateSource": "router_calibration" if calibration_signals else "score_fallback",
            "calibrationConfidenceGate": {
                "minOccurrences": MIN_CALIBRATION_OCCURRENCES,
                "minSampleConfidencePct": MIN_CALIBRATION_CONFIDENCE_PCT,
                "effect": "green_signals_below_threshold_are_downgraded_to_yellow",
            },
            "currentCalibrationSignals": calibration_signals,
            "horizons": config.horizons,
            "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "routerPrinciple": "ATR/振幅/波动超额负责波动天气，中值乖离负责短期拉伸，233MA乖离负责大周期过滤。输出是策略适配天气，不是买卖信号。",
        },
        "current": current,
        "strategyScores": strategy_scores["scores"],
        "deviationFinalWeather": deviation_rules["finalWeather"],
        "currentComponentRows": component_rows,
        "componentSummaryRows": summary_rows,
        "observationRows": volatility_observation_rows,
    }
