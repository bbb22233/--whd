from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from .config import ResearchConfig
from .feature_factory import build_indicator_snapshots, finite, js_number_to_string, js_round, js_sum, safe_divide


BUCKET_DEFS = [
    {"name": "极低", "min": 0, "max": 10},
    {"name": "偏低", "min": 10, "max": 30},
    {"name": "中性", "min": 30, "max": 70},
    {"name": "偏高", "min": 70, "max": 90},
    {"name": "极高", "min": 90, "max": 100.000001},
]

STUDY_DEFS = [
    {
        "kindKey": "middle",
        "kind": "中值",
        "prefix": "中值",
        "rateKey": "middleDeviationRate",
        "atrKey": "middleDeviationAtr",
        "positionKey": "middlePositionPct",
        "pickRate": lambda snapshot: snapshot["position"]["middleDeviationRate"],
        "pickAtr": lambda snapshot: snapshot["position"]["middleDeviationAtr"],
        "pickPosition": lambda snapshot: snapshot["position"]["middlePositionPct"],
    },
    {
        "kindKey": "ma233",
        "kind": "233MA",
        "prefix": "233MA",
        "rateKey": "maDeviationRate",
        "atrKey": "maDeviationAtr",
        "positionKey": "maPositionPct",
        "pickRate": lambda snapshot: snapshot["position"]["maDeviationRate"],
        "pickAtr": lambda snapshot: snapshot["position"]["maDeviationAtr"],
        "pickPosition": lambda snapshot: snapshot["position"]["maPositionPct"],
    },
]

LOW_CONFIDENCE_LABEL = "样本偏少"
DEVIATION_GATE_YELLOW = "黄灯"
DEVIATION_GATE_YELLOW_GREEN = "黄偏绿"


def average(values: list[float]) -> float:
    return js_sum(values) / len(values) if values else 0


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


def bucket_for_rank(rank_percent: float) -> dict[str, Any]:
    for bucket in BUCKET_DEFS:
        if rank_percent >= bucket["min"] and rank_percent < bucket["max"]:
            return bucket
    return BUCKET_DEFS[-1]


def bucket_order(name: str) -> int:
    for index, bucket in enumerate(BUCKET_DEFS):
        if bucket["name"] == name:
            return index
    return -1


def prefix_metric_ranks(snapshots: list[dict[str, Any]], metric_def: dict[str, Any]) -> list[dict[str, Any]]:
    pick = metric_def["pick"]
    unique_values = sorted(set(value for value in (pick(snapshot) for snapshot in snapshots) if finite(value)))
    ranks = {value: index + 1 for index, value in enumerate(unique_values)}
    tree = [0] * (len(unique_values) + 2)
    rows = []
    total = 0

    def add(index: int, value: int) -> None:
        cursor = index
        while cursor < len(tree):
            tree[cursor] += value
            cursor += cursor & -cursor

    def sum_to(index: int) -> int:
        total_at_index = 0
        cursor = index
        while cursor > 0:
            total_at_index += tree[cursor]
            cursor -= cursor & -cursor
        return total_at_index

    for snapshot in snapshots:
        value = pick(snapshot)
        if not finite(value):
            continue
        rank = ranks[value]
        add(rank, 1)
        total += 1
        less = sum_to(rank - 1)
        equal = sum_to(rank) - less
        rows.append({"snapshot": snapshot, "value": value, "rankPct": ((less + (equal * 0.5)) / total) * 100})
    return rows


def classify_deviation(deviation_atr: float, position_percent: float, prefix: str) -> dict[str, Any]:
    abs_deviation = abs(deviation_atr)
    if abs_deviation <= 0.35:
        return {"state": f"{prefix}贴近中轴", "side": 0, "extremity": "near"}
    if deviation_atr > 0:
        extreme = position_percent >= 85 or abs_deviation >= 2.5
        return {"state": f"{prefix}上侧极端" if extreme else f"{prefix}上侧偏离", "side": 1, "extremity": "extreme" if extreme else "deviation"}
    extreme = position_percent <= 15 or abs_deviation >= 2.5
    return {"state": f"{prefix}下侧极端" if extreme else f"{prefix}下侧偏离", "side": -1, "extremity": "extreme" if extreme else "deviation"}


def future_price_stats(candles: list[dict[str, Any]], index: int, horizon: int) -> dict[str, Any] | None:
    entry = candles[index] if 0 <= index < len(candles) else None
    future = candles[index + 1 : index + 1 + horizon]
    if not entry or len(future) < horizon:
        return None
    exit_candle = future[-1]
    max_high = max(candle["high"] for candle in future)
    min_low = min(candle["low"] for candle in future)
    return {
        "futureReturnPct": safe_divide(exit_candle["close"] - entry["close"], entry["close"]) * 100,
        "maxUpPct": safe_divide(max_high - entry["close"], entry["close"]) * 100,
        "maxDownPct": safe_divide(min_low - entry["close"], entry["close"]) * 100,
    }


def future_study_stats(
    snapshot: dict[str, Any],
    future_snapshot: dict[str, Any],
    candles: list[dict[str, Any]],
    study_def: dict[str, Any],
    horizon: int,
) -> dict[str, Any] | None:
    price_stats = future_price_stats(candles, snapshot["index"], horizon)
    if not price_stats:
        return None

    current_atr = study_def["pickAtr"](snapshot)
    future_atr = study_def["pickAtr"](future_snapshot)
    current_abs = abs(current_atr)
    future_abs = abs(future_atr)
    side = 1 if current_atr > 0 else -1 if current_atr < 0 else 0
    future_return_percent = price_stats["futureReturnPct"]
    atr_change_percent = safe_divide(future_snapshot["volatility"]["atrPct"] - snapshot["volatility"]["atrPct"], snapshot["volatility"]["atrPct"]) * 100
    return {
        "futureDeviationAtr": future_atr,
        "futureAbsDeviationAtr": future_abs,
        "distanceChangeAtr": future_abs - current_abs,
        "returnCloser": future_abs < current_abs,
        "continueAway": future_abs > current_abs,
        "crossBaseline": side != 0 and future_atr * side < 0,
        "reversionDirectionHit": future_return_percent < 0 if side > 0 else future_return_percent > 0 if side < 0 else False,
        "continuationDirectionHit": future_return_percent > 0 if side > 0 else future_return_percent < 0 if side < 0 else False,
        "atrChangePct": atr_change_percent,
        "atrUp": atr_change_percent > 0,
        "atrDown": atr_change_percent < 0,
        "strongAtrUp": atr_change_percent >= 10,
        "strongAtrDown": atr_change_percent <= -10,
        **price_stats,
    }


def state_observation_row(
    snapshot: dict[str, Any],
    future_snapshot: dict[str, Any],
    candles: list[dict[str, Any]],
    study_def: dict[str, Any],
    horizon: int,
) -> dict[str, Any] | None:
    stats = future_study_stats(snapshot, future_snapshot, candles, study_def, horizon)
    if not stats:
        return None

    deviation_rate = study_def["pickRate"](snapshot)
    deviation_atr = study_def["pickAtr"](snapshot)
    position_percent = study_def["pickPosition"](snapshot)
    label = classify_deviation(deviation_atr, position_percent, study_def["prefix"])
    return {
        "date": snapshot["date"],
        "kind": study_def["kind"],
        "kindKey": study_def["kindKey"],
        "state": label["state"],
        "side": label["side"],
        "extremity": label["extremity"],
        "horizon": horizon,
        "close": js_round(snapshot["price"]["last"], 2),
        "deviationRate": js_round(deviation_rate),
        "deviationAtr": js_round(deviation_atr),
        "positionPct": js_round(position_percent, 2),
        "futureDeviationAtr": js_round(stats["futureDeviationAtr"]),
        "distanceChangeAtr": js_round(stats["distanceChangeAtr"]),
        "returnCloser": 1 if stats["returnCloser"] else 0,
        "continueAway": 1 if stats["continueAway"] else 0,
        "crossBaseline": 1 if stats["crossBaseline"] else 0,
        "reversionDirectionHit": 1 if stats["reversionDirectionHit"] else 0,
        "continuationDirectionHit": 1 if stats["continuationDirectionHit"] else 0,
        "atrUp": 1 if stats["atrUp"] else 0,
        "atrDown": 1 if stats["atrDown"] else 0,
        "strongAtrUp": 1 if stats["strongAtrUp"] else 0,
        "strongAtrDown": 1 if stats["strongAtrDown"] else 0,
        "atrChangePct": js_round(stats["atrChangePct"]),
        "futureReturnPct": js_round(stats["futureReturnPct"]),
        "maxUpPct": js_round(stats["maxUpPct"]),
        "maxDownPct": js_round(stats["maxDownPct"]),
    }


def metric_defs_for(study_def: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"kind": study_def["kind"], "kindKey": study_def["kindKey"], "metricKey": study_def["rateKey"], "metric": f"{study_def['kind']}乖离率", "unit": "%", "pick": study_def["pickRate"]},
        {"kind": study_def["kind"], "kindKey": study_def["kindKey"], "metricKey": study_def["atrKey"], "metric": f"{study_def['kind']}乖离ATR", "unit": "ATR", "pick": study_def["pickAtr"]},
        {
            "kind": study_def["kind"],
            "kindKey": study_def["kindKey"],
            "metricKey": study_def["positionKey"],
            "metric": f"{study_def['kind']}位置百分位",
            "unit": "percentile",
            "pick": study_def["pickPosition"],
        },
    ]


def rank_rows_by_metric(snapshots: list[dict[str, Any]], study_def: dict[str, Any], metric_def: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in prefix_metric_ranks(snapshots, metric_def):
        bucket = bucket_for_rank(row["rankPct"])
        deviation_atr = study_def["pickAtr"](row["snapshot"])
        position_percent = study_def["pickPosition"](row["snapshot"])
        rows.append(
            {
                **row,
                "rankPct": row["rankPct"],
                "bucket": bucket["name"],
                "bucketRange": f"{bucket['min']}-{min(bucket['max'], 100)}%",
                "stateInfo": classify_deviation(deviation_atr, position_percent, study_def["prefix"]),
            }
        )
    return rows


def metric_observation_rows(
    snapshots: list[dict[str, Any]],
    by_index: dict[int, dict[str, Any]],
    candles: list[dict[str, Any]],
    config: ResearchConfig,
) -> list[dict[str, Any]]:
    rows = []
    for study_def in STUDY_DEFS:
        for metric_def in metric_defs_for(study_def):
            for ranked in rank_rows_by_metric(snapshots, study_def, metric_def):
                for horizon in config.horizons:
                    future_snapshot = by_index.get(ranked["snapshot"]["index"] + horizon)
                    if not future_snapshot:
                        continue
                    stats = future_study_stats(ranked["snapshot"], future_snapshot, candles, study_def, horizon)
                    if not stats:
                        continue
                    rows.append(
                        {
                            "date": ranked["snapshot"]["date"],
                            "kind": metric_def["kind"],
                            "kindKey": metric_def["kindKey"],
                            "metric": metric_def["metric"],
                            "metricKey": metric_def["metricKey"],
                            "unit": metric_def["unit"],
                            "value": js_round(ranked["value"]),
                            "rankPct": js_round(ranked["rankPct"], 2),
                            "bucket": ranked["bucket"],
                            "bucketRange": ranked["bucketRange"],
                            "state": ranked["stateInfo"]["state"],
                            "horizon": horizon,
                            "close": js_round(ranked["snapshot"]["price"]["last"], 2),
                            "returnCloser": 1 if stats["returnCloser"] else 0,
                            "continueAway": 1 if stats["continueAway"] else 0,
                            "crossBaseline": 1 if stats["crossBaseline"] else 0,
                            "reversionDirectionHit": 1 if stats["reversionDirectionHit"] else 0,
                            "continuationDirectionHit": 1 if stats["continuationDirectionHit"] else 0,
                            "atrUp": 1 if stats["atrUp"] else 0,
                            "atrDown": 1 if stats["atrDown"] else 0,
                            "strongAtrUp": 1 if stats["strongAtrUp"] else 0,
                            "strongAtrDown": 1 if stats["strongAtrDown"] else 0,
                            "atrChangePct": js_round(stats["atrChangePct"]),
                            "distanceChangeAtr": js_round(stats["distanceChangeAtr"]),
                            "futureReturnPct": js_round(stats["futureReturnPct"]),
                            "maxUpPct": js_round(stats["maxUpPct"]),
                            "maxDownPct": js_round(stats["maxDownPct"]),
                        }
                    )
    return rows


def summarize_rows(rows: list[dict[str, Any]], key_fields: list[str], extra_fields: dict[str, Callable[[dict[str, Any], list[dict[str, Any]]], Any]] | None = None) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = "::".join(str(row[field]) for field in key_fields)
        groups.setdefault(key, []).append(row)

    result = []
    for group_rows in groups.values():
        first = group_rows[0]
        returns = [row["futureReturnPct"] for row in group_rows]
        distances = [row["distanceChangeAtr"] for row in group_rows]
        atr_changes = [row["atrChangePct"] for row in group_rows]
        max_ups = [row["maxUpPct"] for row in group_rows]
        max_downs = [row["maxDownPct"] for row in group_rows]
        base = {field: first[field] for field in key_fields}
        extra = {key: pick(first, group_rows) for key, pick in (extra_fields or {}).items()}
        result.append(
            {
                **base,
                **extra,
                "occurrences": len(group_rows),
                "returnCloserProbabilityPct": js_round(safe_divide(len([row for row in group_rows if row["returnCloser"] == 1]), len(group_rows)) * 100, 2),
                "continueAwayProbabilityPct": js_round(safe_divide(len([row for row in group_rows if row["continueAway"] == 1]), len(group_rows)) * 100, 2),
                "crossBaselineProbabilityPct": js_round(safe_divide(len([row for row in group_rows if row["crossBaseline"] == 1]), len(group_rows)) * 100, 2),
                "reversionDirectionHitPct": js_round(safe_divide(len([row for row in group_rows if row["reversionDirectionHit"] == 1]), len(group_rows)) * 100, 2),
                "continuationDirectionHitPct": js_round(safe_divide(len([row for row in group_rows if row["continuationDirectionHit"] == 1]), len(group_rows)) * 100, 2),
                "atrUpProbabilityPct": js_round(safe_divide(len([row for row in group_rows if row["atrUp"] == 1]), len(group_rows)) * 100, 2),
                "atrDownProbabilityPct": js_round(safe_divide(len([row for row in group_rows if row["atrDown"] == 1]), len(group_rows)) * 100, 2),
                "strongAtrUpProbabilityPct": js_round(safe_divide(len([row for row in group_rows if row["strongAtrUp"] == 1]), len(group_rows)) * 100, 2),
                "strongAtrDownProbabilityPct": js_round(safe_divide(len([row for row in group_rows if row["strongAtrDown"] == 1]), len(group_rows)) * 100, 2),
                "avgAtrChangePct": js_round(average(atr_changes)),
                "medianAtrChangePct": js_round(median(atr_changes)),
                "avgDistanceChangeAtr": js_round(average(distances)),
                "medianDistanceChangeAtr": js_round(median(distances)),
                "avgReturnPct": js_round(average(returns)),
                "medianReturnPct": js_round(median(returns)),
                "upRatePct": js_round(safe_divide(len([row for row in group_rows if row["futureReturnPct"] > 0]), len(group_rows)) * 100, 2),
                "avgMaxUpPct": js_round(average(max_ups)),
                "avgMaxDownPct": js_round(average(max_downs)),
                "lastSeen": group_rows[-1].get("date") or "",
            }
        )
    return result


def kind_order(kind: str) -> int:
    return {"233MA": 0, "中值": 1}.get(kind, 99)


def state_order(state: str) -> int:
    order = {
        "233MA下侧极端": 0,
        "233MA下侧偏离": 1,
        "233MA贴近中轴": 2,
        "233MA上侧极端": 3,
        "233MA上侧偏离": 4,
        "中值下侧极端": 0,
        "中值下侧偏离": 1,
        "中值贴近中轴": 2,
        "中值上侧极端": 3,
        "中值上侧偏离": 4,
    }
    return order.get(state, 99)


def metric_order(metric: str) -> int:
    order = {
        "233MA乖离ATR": 0,
        "233MA乖离率": 1,
        "233MA位置百分位": 2,
        "中值乖离ATR": 0,
        "中值乖离率": 1,
        "中值位置百分位": 2,
    }
    return order.get(metric, 99)


def summarize_state_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        summarize_rows(
            rows,
            ["kind", "kindKey", "state", "side", "extremity", "horizon"],
            {
                "medianDeviationRate": lambda _, group_rows: js_round(median([row["deviationRate"] for row in group_rows])),
                "medianDeviationAtr": lambda _, group_rows: js_round(median([row["deviationAtr"] for row in group_rows])),
                "medianPositionPct": lambda _, group_rows: js_round(median([row["positionPct"] for row in group_rows]), 2),
            },
        ),
        key=lambda row: (kind_order(row["kind"]), row["horizon"], row["side"], state_order(row["state"])),
    )


def summarize_metric_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        summarize_rows(
            rows,
            ["kind", "kindKey", "metric", "metricKey", "unit", "bucket", "bucketRange", "horizon"],
            {
                "valueMin": lambda _, group_rows: js_round(min(row["value"] for row in group_rows)),
                "valueMedian": lambda _, group_rows: js_round(median([row["value"] for row in group_rows])),
                "valueMax": lambda _, group_rows: js_round(max(row["value"] for row in group_rows)),
            },
        ),
        key=lambda row: (kind_order(row["kind"]), metric_order(row["metric"]), row["horizon"], bucket_order(row["bucket"])),
    )


def contrast_metric_rows(summary_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in summary_rows:
        key = f"{row['kindKey']}::{row['metricKey']}::{row['horizon']}"
        groups.setdefault(key, []).append(row)

    result = []
    for rows in groups.values():
        low = next((row for row in rows if row["bucket"] == "极低"), None)
        high = next((row for row in rows if row["bucket"] == "极高"), None)
        if not low or not high:
            continue
        result.append(
            {
                "kind": low["kind"],
                "kindKey": low["kindKey"],
                "metric": low["metric"],
                "metricKey": low["metricKey"],
                "horizon": low["horizon"],
                "lowOccurrences": low["occurrences"],
                "highOccurrences": high["occurrences"],
                "lowValueMedian": low["valueMedian"],
                "highValueMedian": high["valueMedian"],
                "lowReturnCloserProbabilityPct": low["returnCloserProbabilityPct"],
                "highReturnCloserProbabilityPct": high["returnCloserProbabilityPct"],
                "highMinusLowReturnCloserPct": js_round(high["returnCloserProbabilityPct"] - low["returnCloserProbabilityPct"], 2),
                "lowContinueAwayProbabilityPct": low["continueAwayProbabilityPct"],
                "highContinueAwayProbabilityPct": high["continueAwayProbabilityPct"],
                "highMinusLowContinueAwayPct": js_round(high["continueAwayProbabilityPct"] - low["continueAwayProbabilityPct"], 2),
                "lowAtrUpProbabilityPct": low["atrUpProbabilityPct"],
                "highAtrUpProbabilityPct": high["atrUpProbabilityPct"],
                "highMinusLowAtrUpPct": js_round(high["atrUpProbabilityPct"] - low["atrUpProbabilityPct"], 2),
                "lowAvgReturnPct": low["avgReturnPct"],
                "highAvgReturnPct": high["avgReturnPct"],
                "highMinusLowReturnPct": js_round(high["avgReturnPct"] - low["avgReturnPct"]),
            }
        )
    return sorted(result, key=lambda row: (kind_order(row["kind"]), metric_order(row["metric"]), row["horizon"]))


def percentile_rank(value: Any, values: list[Any]) -> float:
    valid = [item for item in values if finite(item)]
    if not valid:
        return 50
    less = len([item for item in valid if item < value])
    equal = len([item for item in valid if item == value])
    return ((less + (equal * 0.5)) / len(valid)) * 100


def current_rows(selected: list[dict[str, Any]], state_summary_rows: list[dict[str, Any]], horizons: list[int]) -> list[dict[str, Any]]:
    latest = selected[-1] if selected else None
    if not latest:
        return []
    state_by_key = {f"{row['kindKey']}::{row['state']}::{row['horizon']}": row for row in state_summary_rows}

    rows = []
    for study_def in STUDY_DEFS:
        deviation_rate = study_def["pickRate"](latest)
        deviation_atr = study_def["pickAtr"](latest)
        position_percent = study_def["pickPosition"](latest)
        state_info = classify_deviation(deviation_atr, position_percent, study_def["prefix"])
        historical_rate_rank_percent = percentile_rank(deviation_rate, [study_def["pickRate"](snapshot) for snapshot in selected])
        historical_atr_rank_percent = percentile_rank(deviation_atr, [study_def["pickAtr"](snapshot) for snapshot in selected])
        historical_position_rank_percent = percentile_rank(position_percent, [study_def["pickPosition"](snapshot) for snapshot in selected])

        for horizon in horizons:
            summary = state_by_key.get(f"{study_def['kindKey']}::{state_info['state']}::{horizon}")
            rows.append(
                {
                    "date": latest["date"],
                    "close": js_round(latest["price"]["last"], 2),
                    "kind": study_def["kind"],
                    "kindKey": study_def["kindKey"],
                    "state": state_info["state"],
                    "side": state_info["side"],
                    "extremity": state_info["extremity"],
                    "deviationRate": js_round(deviation_rate),
                    "deviationAtr": js_round(deviation_atr),
                    "positionPct": js_round(position_percent, 2),
                    "historicalRateRankPct": js_round(historical_rate_rank_percent, 2),
                    "historicalAtrRankPct": js_round(historical_atr_rank_percent, 2),
                    "historicalPositionRankPct": js_round(historical_position_rank_percent, 2),
                    "horizon": horizon,
                    "similarOccurrences": summary.get("occurrences") if summary else 0,
                    "returnCloserProbabilityPct": summary.get("returnCloserProbabilityPct") if summary else "",
                    "continueAwayProbabilityPct": summary.get("continueAwayProbabilityPct") if summary else "",
                    "crossBaselineProbabilityPct": summary.get("crossBaselineProbabilityPct") if summary else "",
                    "reversionDirectionHitPct": summary.get("reversionDirectionHitPct") if summary else "",
                    "atrUpProbabilityPct": summary.get("atrUpProbabilityPct") if summary else "",
                    "atrDownProbabilityPct": summary.get("atrDownProbabilityPct") if summary else "",
                    "avgAtrChangePct": summary.get("avgAtrChangePct") if summary else "",
                    "medianDistanceChangeAtr": summary.get("medianDistanceChangeAtr") if summary else "",
                }
            )
    return rows


def run_deviation_study_from_snapshots(clean_payload: dict[str, Any], config: ResearchConfig, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [snapshot for snapshot in snapshots if in_window(snapshot["date"], config)]
    by_index = {snapshot["index"]: snapshot for snapshot in snapshots}
    state_observation_rows = []
    for snapshot in selected:
        for study_def in STUDY_DEFS:
            for horizon in config.horizons:
                future_snapshot = by_index.get(snapshot["index"] + horizon)
                if not future_snapshot:
                    continue
                row = state_observation_row(snapshot, future_snapshot, clean_payload["candles"], study_def, horizon)
                if row:
                    state_observation_rows.append(row)

    metric_rows = metric_observation_rows(selected, by_index, clean_payload["candles"], config)
    state_summary_rows = summarize_state_rows(state_observation_rows)
    metric_summary_rows = summarize_metric_rows(metric_rows)
    return {
        "metadata": {
            "instrument": clean_payload["metadata"]["instrument"],
            "bar": clean_payload["metadata"]["bar"],
            "fromDate": config.fromDate,
            "toDate": config.toDate,
            "firstDate": selected[0]["date"] if selected else None,
            "lastDate": selected[-1]["date"] if selected else None,
            "snapshotCount": len(selected),
            "stateObservationRows": len(state_observation_rows),
            "metricObservationRows": len(metric_rows),
            "horizons": config.horizons,
            "bucketScheme": [f"{bucket['name']}:{bucket['min']}-{min(bucket['max'], 100)}%" for bucket in BUCKET_DEFS],
            "metricBucketMode": "causal_prefix_percentile",
            "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        },
        "currentRows": current_rows(selected, state_summary_rows, config.horizons),
        "stateSummaryRows": state_summary_rows,
        "metricSummaryRows": metric_summary_rows,
        "metricContrastRows": contrast_metric_rows(metric_summary_rows),
        "stateObservationRows": state_observation_rows,
        "metricObservationRows": metric_rows,
    }


def run_deviation_study(clean_payload: dict[str, Any], config: ResearchConfig) -> dict[str, Any]:
    return run_deviation_study_from_snapshots(clean_payload, config, build_indicator_snapshots(clean_payload["candles"], config))


def probability_edge(left: Any, right: Any) -> float:
    return abs((float(left) if finite(left) else 0) - (float(right) if finite(right) else 0))


def confidence_label(samples: Any, edge_percent: float) -> str:
    if finite(samples) and samples < 120:
        return LOW_CONFIDENCE_LABEL
    if edge_percent >= 30:
        return "强"
    if edge_percent >= 18:
        return "中强"
    if edge_percent >= 10:
        return "中"
    return "弱"


def is_low_confidence(label: str) -> bool:
    return label == LOW_CONFIDENCE_LABEL


def role_for_kind(kind_key: str) -> str:
    return "短期拉伸/回归" if kind_key == "middle" else "大周期天气过滤"


def rule_for_state(row: dict[str, Any]) -> dict[str, str]:
    state = row.get("state") or ""
    is_middle = row.get("kindKey") == "middle"
    is_ma = row.get("kindKey") == "ma233"
    edge = probability_edge(row.get("returnCloserProbabilityPct"), row.get("continueAwayProbabilityPct"))
    confidence = confidence_label(row.get("occurrences"), edge)

    if is_middle and "下侧极端" in state:
        return {"weatherTag": "短期过冷", "ruleSignal": "回归倾向强", "ruleUse": "适合观察反弹/空头止盈，不直接等于大趋势转多", "riskNote": "如果大周期仍弱，只能当短线天气看"}
    if is_middle and "上侧极端" in state:
        return {"weatherTag": "短期过热", "ruleSignal": "回落倾向强", "ruleUse": "适合观察追多降温/多头止盈，不直接等于做空信号", "riskNote": "强趋势里极端可以延续，必须看波动和量能"}
    if is_middle and "下侧偏离" in state:
        return {"weatherTag": "短期下侧偏离", "ruleSignal": "轻微回归倾向" if confidence == "弱" else "回归倾向", "ruleUse": "只做观察项，等待更极端或其他指标共振", "riskNote": "优势不够大，不能单独触发策略"}
    if is_middle and "上侧偏离" in state:
        return {"weatherTag": "短期上侧偏离", "ruleSignal": "轻微回落倾向" if confidence == "弱" else "回落倾向", "ruleUse": "只做观察项，等待更极端或其他指标共振", "riskNote": "优势不够大，不能单独触发策略"}
    if is_middle and "贴近" in state:
        return {"weatherTag": "短期贴近中轴", "ruleSignal": "方向信息弱", "ruleUse": "不做均值回归依据，更多看波动是否扩张", "riskNote": "贴近中轴时继续拉伸概率通常更高"}
    if is_ma and "下侧极端" in state:
        return {"weatherTag": "大周期弱势深水区", "ruleSignal": "风险过滤", "ruleUse": "禁止仅凭超跌当买点，低吸必须等短期指标和波动确认", "riskNote": "历史上继续远离 233MA 的概率不低"}
    if is_ma and "上侧极端" in state:
        return {"weatherTag": "大周期强势高位", "ruleSignal": "趋势过滤", "ruleUse": "不把高乖离直接当做空信号，更多提示追高风险", "riskNote": "强势区可以长期维持在 233MA 上方"}
    if is_ma and "下侧偏离" in state:
        return {"weatherTag": "大周期偏弱", "ruleSignal": "谨慎过滤", "ruleUse": "趋势多头降权，反弹策略需要更严格确认", "riskNote": "未到极端，但大天气仍偏弱"}
    if is_ma and "上侧偏离" in state:
        return {"weatherTag": "大周期偏强", "ruleSignal": "顺势过滤", "ruleUse": "趋势策略可加权，均值回落只当降温提示", "riskNote": "不是天然做空区域"}
    return {"weatherTag": "大周期中轴附近", "ruleSignal": "方向切换区", "ruleUse": "不做趋势天气判断，等待方向重新拉开", "riskNote": "中轴附近容易出现反复"}


def rule_library_row(row: dict[str, Any]) -> dict[str, Any]:
    rule = rule_for_state(row)
    edge = probability_edge(row["returnCloserProbabilityPct"], row["continueAwayProbabilityPct"])
    return {
        "kind": row["kind"],
        "kindKey": row["kindKey"],
        "role": role_for_kind(row["kindKey"]),
        "state": row["state"],
        "horizon": row["horizon"],
        "weatherTag": rule["weatherTag"],
        "ruleSignal": rule["ruleSignal"],
        "ruleUse": rule["ruleUse"],
        "riskNote": rule["riskNote"],
        "confidence": confidence_label(row["occurrences"], edge),
        "probabilityEdgePct": js_round(edge, 2),
        "occurrences": row["occurrences"],
        "medianDeviationRate": row["medianDeviationRate"],
        "medianDeviationAtr": row["medianDeviationAtr"],
        "medianPositionPct": row["medianPositionPct"],
        "returnCloserProbabilityPct": row["returnCloserProbabilityPct"],
        "continueAwayProbabilityPct": row["continueAwayProbabilityPct"],
        "crossBaselineProbabilityPct": row["crossBaselineProbabilityPct"],
        "reversionDirectionHitPct": row["reversionDirectionHitPct"],
        "atrUpProbabilityPct": row["atrUpProbabilityPct"],
        "atrDownProbabilityPct": row["atrDownProbabilityPct"],
        "medianDistanceChangeAtr": row["medianDistanceChangeAtr"],
        "avgReturnPct": row["avgReturnPct"],
    }


def current_rule_row(row: dict[str, Any]) -> dict[str, Any]:
    rule = rule_for_state(row)
    edge = probability_edge(row["returnCloserProbabilityPct"], row["continueAwayProbabilityPct"])
    return {
        "date": row["date"],
        "close": row["close"],
        "kind": row["kind"],
        "kindKey": row["kindKey"],
        "role": role_for_kind(row["kindKey"]),
        "state": row["state"],
        "horizon": row["horizon"],
        "weatherTag": rule["weatherTag"],
        "ruleSignal": rule["ruleSignal"],
        "ruleUse": rule["ruleUse"],
        "riskNote": rule["riskNote"],
        "confidence": confidence_label(row["similarOccurrences"], edge),
        "probabilityEdgePct": js_round(edge, 2),
        "deviationRate": row["deviationRate"],
        "deviationAtr": row["deviationAtr"],
        "positionPct": row["positionPct"],
        "historicalRateRankPct": row["historicalRateRankPct"],
        "historicalAtrRankPct": row["historicalAtrRankPct"],
        "historicalPositionRankPct": row["historicalPositionRankPct"],
        "similarOccurrences": row["similarOccurrences"],
        "returnCloserProbabilityPct": row["returnCloserProbabilityPct"],
        "continueAwayProbabilityPct": row["continueAwayProbabilityPct"],
        "crossBaselineProbabilityPct": row["crossBaselineProbabilityPct"],
        "reversionDirectionHitPct": row["reversionDirectionHitPct"],
        "atrUpProbabilityPct": row["atrUpProbabilityPct"],
        "atrDownProbabilityPct": row["atrDownProbabilityPct"],
        "avgAtrChangePct": row["avgAtrChangePct"],
        "medianDistanceChangeAtr": row["medianDistanceChangeAtr"],
    }


def find_current(current_rule_rows: list[dict[str, Any]], kind_key: str, horizon: int) -> dict[str, Any] | None:
    return next((row for row in current_rule_rows if row["kindKey"] == kind_key and row["horizon"] == horizon), None)


def final_weather(current_rule_rows: list[dict[str, Any]]) -> dict[str, Any]:
    middle10 = find_current(current_rule_rows, "middle", 10)
    ma10 = find_current(current_rule_rows, "ma233", 10)
    if not middle10 or not ma10:
        return {"weather": "数据不足", "shortTerm": "未知", "bigCycle": "未知", "actionBias": "等待数据补齐"}

    middle_rule = rule_for_state(middle10)
    ma_rule = rule_for_state(ma10)
    middle_edge = probability_edge(middle10["returnCloserProbabilityPct"], middle10["continueAwayProbabilityPct"])
    ma_edge = probability_edge(ma10["returnCloserProbabilityPct"], ma10["continueAwayProbabilityPct"])
    middle_confidence = confidence_label(middle10["similarOccurrences"], middle_edge)
    ma_confidence = confidence_label(ma10["similarOccurrences"], ma_edge)
    confidence_limited = is_low_confidence(middle_confidence) or is_low_confidence(ma_confidence)
    short_bias = "短期略偏回归" if middle10["returnCloserProbabilityPct"] > middle10["continueAwayProbabilityPct"] else "短期仍可能继续拉伸"
    big_bias = "大周期偏弱" if "下侧" in ma10["state"] else "大周期偏强" if "上侧" in ma10["state"] else "大周期中性"
    is_weak_big_cycle = "下侧极端" in ma10["state"] or "下侧偏离" in ma10["state"]
    is_middle_extreme = "极端" in middle10["state"]

    action_bias = "观察"
    gate = "黄灯"
    if is_weak_big_cycle and not is_middle_extreme:
        action_bias = "不把短期下偏当买点，等待更强共振"
        gate = "黄偏红"
    elif is_weak_big_cycle and is_middle_extreme and "下侧" in middle10["state"]:
        action_bias = "可观察短线回归，但仍受大周期弱势约束"
        gate = "黄灯"
    elif not is_weak_big_cycle and is_middle_extreme:
        action_bias = "短期回归信号更干净"
        gate = "黄偏绿"

    if confidence_limited and gate == DEVIATION_GATE_YELLOW_GREEN:
        action_bias = "样本偏少，偏离规则只做观察，不升级主灯号"
        gate = DEVIATION_GATE_YELLOW

    short_probability = js_number_to_string(middle10["returnCloserProbabilityPct"])
    big_probability = js_number_to_string(ma10["continueAwayProbabilityPct"])

    return {
        "date": middle10["date"],
        "close": middle10["close"],
        "weather": f"{middle_rule['weatherTag']} + {ma_rule['weatherTag']}",
        "shortTerm": f"{short_bias}，10日回归概率 {short_probability}%",
        "bigCycle": f"{big_bias}，10日继续远离概率 {big_probability}%",
        "gate": gate,
        "actionBias": action_bias,
        "ruleConfidence": f"中值{middle_confidence} / 233MA{ma_confidence}",
        "confidenceLimited": confidence_limited,
        "riskNote": f"{middle_rule['riskNote']}；{ma_rule['riskNote']}",
    }


def build_deviation_rules(deviation_study_result: dict[str, Any]) -> dict[str, Any]:
    rule_library_rows = [rule_library_row(row) for row in deviation_study_result["stateSummaryRows"]]
    current_rule_rows = [current_rule_row(row) for row in deviation_study_result["currentRows"]]
    return {
        "metadata": {
            **deviation_study_result["metadata"],
            "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "rulePrinciple": "中值乖离负责短期拉伸/回归，233MA乖离负责大周期天气过滤。规则只识别状态，不直接给交易方向。",
        },
        "finalWeather": final_weather(current_rule_rows),
        "currentRuleRows": current_rule_rows,
        "ruleLibraryRows": rule_library_rows,
    }


def build_deviation_rules_from_clean(clean_payload: dict[str, Any], config: ResearchConfig) -> dict[str, Any]:
    return build_deviation_rules(run_deviation_study(clean_payload, config))
