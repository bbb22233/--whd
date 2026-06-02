from __future__ import annotations

from datetime import datetime, timezone
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
    return {"scores": scores, "topRoute": route_result["topRoutes"][0] if route_result["topRoutes"] else scores[0], "routeResult": route_result}


def build_market_weather_router_components(clean_payload: dict[str, Any], config: ResearchConfig) -> dict[str, Any]:
    snapshots = build_indicator_snapshots(clean_payload["candles"], config)
    selected = [snapshot for snapshot in snapshots if in_window(snapshot["date"], config)]
    latest = selected[-1] if selected else None
    volatility_observation_rows = observation_rows(snapshots, config)
    summary_rows = component_summary_rows(volatility_observation_rows)
    component_rows = current_component_rows(latest, summary_rows, config) if latest else []
    strategy_scores = score_route_strategies(latest, config)["scores"] if latest else []
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
            "horizons": config.horizons,
            "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "pythonParityScope": "router_components_without_deviation_or_calibration",
        },
        "strategyScores": strategy_scores,
        "currentComponentRows": component_rows,
        "componentSummaryRows": summary_rows,
        "observationRows": volatility_observation_rows,
    }
