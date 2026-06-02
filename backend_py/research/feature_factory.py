from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Callable

from .config import ResearchConfig


FeatureDef = dict[str, Any]


def finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def safe_divide(numerator: Any, denominator: Any) -> float:
    if not finite(numerator) or not finite(denominator) or denominator == 0:
        return 0
    return numerator / denominator


def clamp(value: Any, minimum: float, maximum: float) -> float:
    if not finite(value):
        return minimum
    return min(maximum, max(minimum, value))


def js_round(value: Any, digits: int = 4) -> float:
    if not finite(value):
        return 0
    factor = 10**digits
    number = float(value) * factor
    if number >= 0:
        return math.floor(number + 0.5) / factor
    return math.ceil(number - 0.5) / factor


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0


def percent_change(current: float, previous: float) -> float:
    return safe_divide(current - previous, previous) * 100


def rolling_slice(values: list[Any], end_index: int, length: int) -> list[Any]:
    return values[max(0, end_index - length + 1) : end_index + 1]


def high_low_middle(candles: list[dict[str, Any]], end_index: int, length: int) -> float | None:
    window = rolling_slice(candles, end_index, length)
    if len(window) < length:
        return None
    return (max(candle["high"] for candle in window) + min(candle["low"] for candle in window)) / 2


def simple_moving_average(values: list[float], end_index: int, length: int) -> float | None:
    window = rolling_slice(values, end_index, length)
    if len(window) < length:
        return None
    return average(window)


def true_ranges(candles: list[dict[str, Any]]) -> list[float]:
    ranges = []
    for index, candle in enumerate(candles):
        if index == 0:
            ranges.append(candle["high"] - candle["low"])
            continue
        previous_close = candles[index - 1]["close"]
        ranges.append(max(candle["high"] - candle["low"], abs(candle["high"] - previous_close), abs(candle["low"] - previous_close)))
    return ranges


def wilder_atr(candles: list[dict[str, Any]], period: int) -> list[float | None]:
    ranges = true_ranges(candles)
    atr_values: list[float | None] = [None] * len(candles)
    if len(ranges) < period:
        return atr_values
    previous_atr = average(ranges[:period])
    atr_values[period - 1] = previous_atr
    for index in range(period, len(ranges)):
        previous_atr = ((previous_atr * (period - 1)) + ranges[index]) / period
        atr_values[index] = previous_atr
    return atr_values


def deviation_in_atr(price: float, baseline: float | None, atr: float | None) -> float | None:
    if not baseline or not atr:
        return None
    deviation_rate = safe_divide(price - baseline, baseline)
    atr_rate = safe_divide(atr, baseline)
    return safe_divide(deviation_rate, atr_rate)


def position_pct(current: float | None, valley: float | None, peak: float | None) -> float:
    if not finite(current) or not finite(valley) or not finite(peak) or peak == valley:
        return 50
    return clamp(((current - valley) / (peak - valley)) * 100, 0, 100)


def resonance(values: list[float]) -> dict[str, Any]:
    up_count = len([value for value in values if value > 0])
    down_count = len([value for value in values if value < 0])
    if up_count >= 3:
        return {"direction": "up", "count": up_count}
    if down_count >= 3:
        return {"direction": "down", "count": down_count}
    return {"direction": "mixed", "count": max(up_count, down_count)}


def prefix_extrema(values: list[float | None]) -> dict[str, list[float | None]]:
    peaks: list[float | None] = [None] * len(values)
    valleys: list[float | None] = [None] * len(values)
    peak = -math.inf
    valley = math.inf
    for index, value in enumerate(values):
        if finite(value):
            peak = max(peak, value)
            valley = min(valley, value)
        peaks[index] = peak if finite(peak) else None
        valleys[index] = valley if finite(valley) else None
    return {"peaks": peaks, "valleys": valleys}


def prefix_percentile(values: list[float | None]) -> list[float | None]:
    unique_values = sorted(set(value for value in values if finite(value)))
    ranks = {value: index + 1 for index, value in enumerate(unique_values)}
    tree = [0] * (len(unique_values) + 2)
    result: list[float | None] = []
    total = 0

    def add(rank: int, value: int) -> None:
        cursor = rank
        while cursor < len(tree):
            tree[cursor] += value
            cursor += cursor & -cursor

    def sum_to(rank: int) -> int:
        cursor = rank
        total_at_index = 0
        while cursor > 0:
            total_at_index += tree[cursor]
            cursor -= cursor & -cursor
        return total_at_index

    for value in values:
        if not finite(value):
            result.append(None)
            continue
        rank = ranks[value]
        add(rank, 1)
        total += 1
        less = sum_to(rank - 1)
        equal = sum_to(rank) - less
        result.append(((less + (equal * 0.5)) / total) * 100)
    return result


def build_atr_bundle(candles: list[dict[str, Any]], period: int) -> dict[str, Any]:
    atr_values = wilder_atr(candles, period)
    atr_pct_values = [safe_divide(atr_values[index], candle["close"]) * 100 if atr_values[index] else None for index, candle in enumerate(candles)]
    multiple_values = [safe_divide(candle["high"] - candle["low"], atr_values[index]) if atr_values[index] else None for index, candle in enumerate(candles)]
    return {
        "period": period,
        "atrValues": atr_values,
        "atrPctValues": atr_pct_values,
        "atrPercentileValues": prefix_percentile(atr_pct_values),
        "multipleValues": multiple_values,
        "multiplePercentileValues": prefix_percentile(multiple_values),
    }


def build_indicator_snapshots(candles: list[dict[str, Any]], config: ResearchConfig) -> list[dict[str, Any]]:
    indicator = config.indicator
    closes = [candle["close"] for candle in candles]
    atr_values = wilder_atr(candles, indicator.atrPeriod)
    atr_pct_values = [safe_divide(atr_values[index], candle["close"]) * 100 if atr_values[index] else None for index, candle in enumerate(candles)]
    volatility_multiple_values = [safe_divide(candle["high"] - candle["low"], atr_values[index]) if atr_values[index] else None for index, candle in enumerate(candles)]
    atr_percentile_values = prefix_percentile(atr_pct_values)
    volatility_multiple_percentile_values = prefix_percentile(volatility_multiple_values)
    fib_atr_bundles = {str(period): build_atr_bundle(candles, period) for period in indicator.fibAtrPeriods}
    middle_values = [high_low_middle(candles, index, indicator.middlePeriod) for index in range(len(candles))]
    ma_values = [simple_moving_average(closes, index, indicator.maPeriod) for index in range(len(candles))]
    middle_deviation_atr_values = [deviation_in_atr(candle["close"], middle_values[index], atr_values[index]) for index, candle in enumerate(candles)]
    ma_deviation_atr_values = [deviation_in_atr(candle["close"], ma_values[index], atr_values[index]) for index, candle in enumerate(candles)]
    middle_extrema = prefix_extrema(middle_deviation_atr_values)
    ma_extrema = prefix_extrema(ma_deviation_atr_values)
    warmup = max(indicator.maPeriod - 1, indicator.middlePeriod - 1, indicator.atrPeriod - 1, max(indicator.momentumPeriods))
    snapshots = []

    for index in range(warmup, len(candles)):
        latest = candles[index]
        atr_abs = atr_values[index]
        middle = middle_values[index]
        ma233 = ma_values[index]
        middle_deviation_atr = middle_deviation_atr_values[index]
        ma_deviation_atr = ma_deviation_atr_values[index]
        middle_peak_atr = middle_extrema["peaks"][index]
        middle_valley_atr = middle_extrema["valleys"][index]
        ma_peak_atr = ma_extrema["peaks"][index]
        ma_valley_atr = ma_extrema["valleys"][index]
        atr_pct = atr_pct_values[index]
        volatility_multiple = volatility_multiple_values[index]
        atr_percentile = atr_percentile_values[index]
        volatility_multiple_percentile = volatility_multiple_percentile_values[index]
        if not atr_abs or not middle or not ma233 or middle_deviation_atr is None or ma_deviation_atr is None:
            continue
        if atr_pct is None or volatility_multiple is None or atr_percentile is None or volatility_multiple_percentile is None:
            continue
        if middle_peak_atr is None or middle_valley_atr is None or ma_peak_atr is None or ma_valley_atr is None:
            continue

        previous_volumes = [candle["volume"] for candle in candles[max(0, index - indicator.volumeMaPeriod) : index]]
        volume_ma = average(previous_volumes)
        momentum_values = {f"d{period}": percent_change(latest["close"], candles[index - period]["close"]) for period in indicator.momentumPeriods}
        trend_score = sum(momentum_values[f"d{period}"] * indicator.trendWeights.get(str(period), 0) for period in indicator.momentumPeriods)
        resonance_state = resonance([momentum_values[f"d{period}"] for period in indicator.momentumPeriods])
        middle_position_pct = position_pct(middle_deviation_atr, middle_valley_atr, middle_peak_atr)
        ma_position_pct = position_pct(ma_deviation_atr, ma_valley_atr, ma_peak_atr)
        range_abs = latest["high"] - latest["low"]
        range_pct_close = safe_divide(range_abs, latest["close"]) * 100
        remaining_momentum_abs = range_abs - atr_abs
        remaining_momentum_pct = range_pct_close - atr_pct
        remaining_momentum_atr = volatility_multiple - 1
        fib_atr = {}
        for period, bundle in fib_atr_bundles.items():
            fib_atr_abs = bundle["atrValues"][index]
            fib_atr_pct = bundle["atrPctValues"][index]
            fib_multiple = bundle["multipleValues"][index]
            fib_atr_percentile = bundle["atrPercentileValues"][index]
            fib_multiple_percentile = bundle["multiplePercentileValues"][index]
            if not fib_atr_abs or fib_atr_pct is None or fib_multiple is None or fib_atr_percentile is None or fib_multiple_percentile is None:
                continue
            fib_atr[period] = {
                "atrAbs": fib_atr_abs,
                "atrPct": fib_atr_pct,
                "atrPercentile": fib_atr_percentile,
                "multiple": fib_multiple,
                "multiplePercentile": fib_multiple_percentile,
                "remainingMomentumAbs": range_abs - fib_atr_abs,
                "remainingMomentumPct": range_pct_close - fib_atr_pct,
                "remainingMomentumAtr": fib_multiple - 1,
            }
        fib_atr_comparisons = {
            "atr3To21": safe_divide(fib_atr.get("3", {}).get("atrAbs"), fib_atr.get("21", {}).get("atrAbs")) if fib_atr.get("3") and fib_atr.get("21") else 0,
            "atr8To21": safe_divide(fib_atr.get("8", {}).get("atrAbs"), fib_atr.get("21", {}).get("atrAbs")) if fib_atr.get("8") and fib_atr.get("21") else 0,
            "atr13To21": safe_divide(fib_atr.get("13", {}).get("atrAbs"), fib_atr.get("21", {}).get("atrAbs")) if fib_atr.get("13") and fib_atr.get("21") else 0,
            "atr3To8": safe_divide(fib_atr.get("3", {}).get("atrAbs"), fib_atr.get("8", {}).get("atrAbs")) if fib_atr.get("3") and fib_atr.get("8") else 0,
            "atr8To13": safe_divide(fib_atr.get("8", {}).get("atrAbs"), fib_atr.get("13", {}).get("atrAbs")) if fib_atr.get("8") and fib_atr.get("13") else 0,
        }

        snapshots.append(
            {
                "index": index,
                "date": latest["date"],
                "openTime": latest.get("openTime"),
                "price": {
                    "last": latest["close"],
                    "open": latest["open"],
                    "high": latest["high"],
                    "low": latest["low"],
                    "changePct": percent_change(latest["close"], latest["open"]),
                },
                "volatility": {
                    "rangeAbs": range_abs,
                    "rangePct": safe_divide(range_abs, latest["open"]) * 100,
                    "atrAbs": atr_abs,
                    "atrPct": atr_pct,
                    "atrPercentile": atr_percentile,
                    "multiple": volatility_multiple,
                    "multiplePercentile": volatility_multiple_percentile,
                    "excess": volatility_multiple - 1,
                    "remainingMomentumAbs": remaining_momentum_abs,
                    "remainingMomentumPct": remaining_momentum_pct,
                    "remainingMomentumAtr": remaining_momentum_atr,
                    "fibAtr": fib_atr,
                    "fibAtrComparisons": fib_atr_comparisons,
                },
                "volume": {"current": latest["volume"], "ma20": volume_ma, "multiple": safe_divide(latest["volume"], volume_ma)},
                "momentum": {**momentum_values, "trendScore": trend_score, "resonanceDirection": resonance_state["direction"], "resonanceCount": resonance_state["count"]},
                "position": {
                    "middle": middle,
                    "ma233": ma233,
                    "middleDeviationRate": safe_divide(latest["close"] - middle, middle) * 100,
                    "middleDeviationAtr": middle_deviation_atr,
                    "middlePeakAtr": middle_peak_atr,
                    "middleValleyAtr": middle_valley_atr,
                    "middlePositionPct": middle_position_pct,
                    "maDeviationRate": safe_divide(latest["close"] - ma233, ma233) * 100,
                    "maDeviationAtr": ma_deviation_atr,
                    "maPeakAtr": ma_peak_atr,
                    "maValleyAtr": ma_valley_atr,
                    "maPositionPct": ma_position_pct,
                    "stretchHeat": clamp(abs(middle_position_pct - 50) + abs(ma_position_pct - 50), 0, 100),
                },
            }
        )
    return snapshots


def feature_defs() -> list[tuple[str, str, Callable[[dict[str, Any]], float]]]:
    return [
        ("rangePct", "振幅率", lambda s: s["volatility"]["rangePct"]),
        ("atrPct", "ATR率", lambda s: s["volatility"]["atrPct"]),
        ("atrPercentile", "ATR百分位", lambda s: s["volatility"]["atrPercentile"]),
        ("volatilityMultiple", "波动倍率", lambda s: s["volatility"]["multiple"]),
        ("volatilityMultiplePercentile", "波动倍率百分位", lambda s: s["volatility"]["multiplePercentile"]),
        ("volatilityExcess", "波动超额", lambda s: s["volatility"]["excess"]),
        ("remainingMomentumPct", "波动超额率", lambda s: s["volatility"]["remainingMomentumPct"]),
        ("remainingMomentumAtr", "波动超额ATR", lambda s: s["volatility"]["remainingMomentumAtr"]),
        ("atr3Pct", "3日ATR率", lambda s: s["volatility"]["fibAtr"]["3"]["atrPct"]),
        ("atr8Pct", "8日ATR率", lambda s: s["volatility"]["fibAtr"]["8"]["atrPct"]),
        ("atr13Pct", "13日ATR率", lambda s: s["volatility"]["fibAtr"]["13"]["atrPct"]),
        ("atr21Pct", "21日ATR率", lambda s: s["volatility"]["fibAtr"]["21"]["atrPct"]),
        ("atr3Percentile", "3日ATR百分位", lambda s: s["volatility"]["fibAtr"]["3"]["atrPercentile"]),
        ("atr8Percentile", "8日ATR百分位", lambda s: s["volatility"]["fibAtr"]["8"]["atrPercentile"]),
        ("atr13Percentile", "13日ATR百分位", lambda s: s["volatility"]["fibAtr"]["13"]["atrPercentile"]),
        ("atr21Percentile", "21日ATR百分位", lambda s: s["volatility"]["fibAtr"]["21"]["atrPercentile"]),
        ("volatilityMultiple3", "振幅/3日ATR", lambda s: s["volatility"]["fibAtr"]["3"]["multiple"]),
        ("volatilityMultiple8", "振幅/8日ATR", lambda s: s["volatility"]["fibAtr"]["8"]["multiple"]),
        ("volatilityMultiple13", "振幅/13日ATR", lambda s: s["volatility"]["fibAtr"]["13"]["multiple"]),
        ("volatilityMultiple21", "振幅/21日ATR", lambda s: s["volatility"]["fibAtr"]["21"]["multiple"]),
        ("volatilityMultiple3Percentile", "振幅/3日ATR百分位", lambda s: s["volatility"]["fibAtr"]["3"]["multiplePercentile"]),
        ("volatilityMultiple8Percentile", "振幅/8日ATR百分位", lambda s: s["volatility"]["fibAtr"]["8"]["multiplePercentile"]),
        ("volatilityMultiple13Percentile", "振幅/13日ATR百分位", lambda s: s["volatility"]["fibAtr"]["13"]["multiplePercentile"]),
        ("volatilityMultiple21Percentile", "振幅/21日ATR百分位", lambda s: s["volatility"]["fibAtr"]["21"]["multiplePercentile"]),
        ("remainingMomentumAtr3", "3日波动超额ATR", lambda s: s["volatility"]["fibAtr"]["3"]["remainingMomentumAtr"]),
        ("remainingMomentumAtr8", "8日波动超额ATR", lambda s: s["volatility"]["fibAtr"]["8"]["remainingMomentumAtr"]),
        ("remainingMomentumAtr13", "13日波动超额ATR", lambda s: s["volatility"]["fibAtr"]["13"]["remainingMomentumAtr"]),
        ("remainingMomentumAtr21", "21日波动超额ATR", lambda s: s["volatility"]["fibAtr"]["21"]["remainingMomentumAtr"]),
        ("atr3To21", "3/21日ATR比", lambda s: s["volatility"]["fibAtrComparisons"]["atr3To21"]),
        ("atr8To21", "8/21日ATR比", lambda s: s["volatility"]["fibAtrComparisons"]["atr8To21"]),
        ("atr13To21", "13/21日ATR比", lambda s: s["volatility"]["fibAtrComparisons"]["atr13To21"]),
        ("atr3To8", "3/8日ATR比", lambda s: s["volatility"]["fibAtrComparisons"]["atr3To8"]),
        ("atr8To13", "8/13日ATR比", lambda s: s["volatility"]["fibAtrComparisons"]["atr8To13"]),
        ("volumeMultiple", "量能倍率", lambda s: s["volume"]["multiple"]),
        ("d8", "8日涨跌", lambda s: s["momentum"]["d8"]),
        ("d13", "13日涨跌", lambda s: s["momentum"]["d13"]),
        ("d21", "21日涨跌", lambda s: s["momentum"]["d21"]),
        ("d34", "34日涨跌", lambda s: s["momentum"]["d34"]),
        ("trendScore", "趋势动能", lambda s: s["momentum"]["trendScore"]),
        ("resonanceCount", "共振数量", lambda s: s["momentum"]["resonanceCount"]),
        ("middleDeviationRate", "中值乖离率", lambda s: s["position"]["middleDeviationRate"]),
        ("middleDeviationAtr", "中值乖离ATR", lambda s: s["position"]["middleDeviationAtr"]),
        ("middlePositionPct", "中值位置百分位", lambda s: s["position"]["middlePositionPct"]),
        ("maDeviationRate", "233MA乖离率", lambda s: s["position"]["maDeviationRate"]),
        ("maDeviationAtr", "233MA乖离ATR", lambda s: s["position"]["maDeviationAtr"]),
        ("maPositionPct", "MA位置百分位", lambda s: s["position"]["maPositionPct"]),
        ("stretchHeat", "拉伸热度", lambda s: s["position"]["stretchHeat"]),
    ]


def make_running_stats() -> dict[str, dict[str, Any]]:
    return {key: {"key": key, "label": label, "count": 0, "mean": 0, "m2": 0, "min": math.inf, "max": -math.inf} for key, label, _ in feature_defs()}


def update_running_stats(stats: dict[str, dict[str, Any]], values: dict[str, float]) -> None:
    for key, _, _ in feature_defs():
        item = stats[key]
        value = values[key]
        item["count"] += 1
        delta = value - item["mean"]
        item["mean"] += delta / item["count"]
        delta_after_mean = value - item["mean"]
        item["m2"] += delta * delta_after_mean
        item["min"] = min(item["min"], value)
        item["max"] = max(item["max"], value)


def finalize_running_stats(item: dict[str, Any]) -> dict[str, Any]:
    std = 1 if item["count"] < 2 else math.sqrt(item["m2"] / item["count"]) or 1
    return {"key": item["key"], "label": item["label"], "mean": item["mean"], "std": std, "min": item["min"] if item["count"] else 0, "max": item["max"] if item["count"] else 0, "count": item["count"]}


def snapshot_running_stats(stats: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {key: finalize_running_stats(stats[key]) for key, _, _ in feature_defs()}


def build_feature_dataset(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    raw_rows = []
    for snapshot in snapshots:
        values = {key: pick(snapshot) for key, _, pick in feature_defs()}
        if all(finite(value) for value in values.values()):
            raw_rows.append({"date": snapshot["date"], "index": snapshot["index"], "close": snapshot["price"]["last"], "values": values, "snapshot": snapshot})

    running_stats = make_running_stats()
    rows = []
    for row in raw_rows:
        update_running_stats(running_stats, row["values"])
        row_stats = snapshot_running_stats(running_stats)
        vector = []
        for key, _, _ in feature_defs():
            feature_stats = row_stats[key]
            vector.append(clamp((row["values"][key] - feature_stats["mean"]) / feature_stats["std"], -5, 5))
        rows.append({**row, "vector": vector})

    return {
        "features": [{"key": key, "label": label} for key, label, _ in feature_defs()],
        "stats": snapshot_running_stats(running_stats),
        "normalization": {"mode": "expanding_causal_zscore", "description": "Each row vector uses running mean/std from rows up to and including that row."},
        "rows": rows,
    }


def in_window(date: str, config: ResearchConfig) -> bool:
    if config.fromDate and date < config.fromDate:
        return False
    if config.toDate and date > config.toDate:
        return False
    return True


def build_feature_factory_dataset(clean_payload: dict[str, Any], config: ResearchConfig) -> dict[str, Any]:
    snapshots = [snapshot for snapshot in build_indicator_snapshots(clean_payload["candles"], config) if in_window(snapshot["date"], config)]
    return {"snapshots": snapshots, "dataset": build_feature_dataset(snapshots)}


def build_feature_factory_core(clean_payload: dict[str, Any], config: ResearchConfig) -> dict[str, Any]:
    bundle = build_feature_factory_dataset(clean_payload, config)
    snapshots = bundle["snapshots"]
    dataset = bundle["dataset"]
    latest = dataset["rows"][-1] if dataset["rows"] else None
    return {
        "metadata": {
            "instrument": clean_payload["metadata"]["instrument"],
            "bar": clean_payload["metadata"]["bar"],
            "fromDate": config.fromDate,
            "toDate": config.toDate,
            "firstDate": snapshots[0]["date"] if snapshots else None,
            "lastDate": snapshots[-1]["date"] if snapshots else None,
            "snapshotCount": len(snapshots),
            "featureCount": len(dataset["features"]),
            "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "pythonParityScope": "core_features_without_weather_labels_or_strategy_routes",
        },
        "features": dataset["features"],
        "featureStats": dataset["stats"],
        "current": {
            "date": latest["snapshot"]["date"],
            "close": js_round(latest["snapshot"]["price"]["last"], 2),
            "values": {key: js_round(value) for key, value in latest["values"].items()},
        }
        if latest
        else None,
        "featureRows": [feature_csv_row(row) for row in dataset["rows"]],
    }


def feature_csv_row(row: dict[str, Any]) -> dict[str, Any]:
    snapshot = row["snapshot"]
    values = row["values"]
    return {
        "date": snapshot["date"],
        "close": js_round(snapshot["price"]["last"], 2),
        "changePct": js_round(snapshot["price"]["changePct"]),
        "rangePct": js_round(snapshot["volatility"]["rangePct"]),
        "atrPct": js_round(snapshot["volatility"]["atrPct"]),
        "atrPercentile": js_round(snapshot["volatility"]["atrPercentile"], 2),
        "volatilityMultiple": js_round(snapshot["volatility"]["multiple"]),
        "volatilityMultiplePercentile": js_round(snapshot["volatility"]["multiplePercentile"], 2),
        "remainingMomentumAtr": js_round(snapshot["volatility"]["remainingMomentumAtr"]),
        "atr3Pct": js_round(snapshot["volatility"]["fibAtr"]["3"]["atrPct"]),
        "atr8Pct": js_round(snapshot["volatility"]["fibAtr"]["8"]["atrPct"]),
        "atr13Pct": js_round(snapshot["volatility"]["fibAtr"]["13"]["atrPct"]),
        "atr21Pct": js_round(snapshot["volatility"]["fibAtr"]["21"]["atrPct"]),
        "atr3To21": js_round(snapshot["volatility"]["fibAtrComparisons"]["atr3To21"]),
        "atr8To21": js_round(snapshot["volatility"]["fibAtrComparisons"]["atr8To21"]),
        "volumeMultiple": js_round(snapshot["volume"]["multiple"]),
        "d8": js_round(snapshot["momentum"]["d8"]),
        "d13": js_round(snapshot["momentum"]["d13"]),
        "d21": js_round(snapshot["momentum"]["d21"]),
        "d34": js_round(snapshot["momentum"]["d34"]),
        "trendScore": js_round(snapshot["momentum"]["trendScore"]),
        "resonanceDirection": snapshot["momentum"]["resonanceDirection"],
        "resonanceCount": snapshot["momentum"]["resonanceCount"],
        "middleDeviationRate": js_round(snapshot["position"]["middleDeviationRate"]),
        "middleDeviationAtr": js_round(snapshot["position"]["middleDeviationAtr"]),
        "middlePositionPct": js_round(snapshot["position"]["middlePositionPct"], 2),
        "maDeviationRate": js_round(snapshot["position"]["maDeviationRate"]),
        "maDeviationAtr": js_round(snapshot["position"]["maDeviationAtr"]),
        "maPositionPct": js_round(snapshot["position"]["maPositionPct"], 2),
        "stretchHeat": js_round(snapshot["position"]["stretchHeat"], 2),
        **{f"value_{key}": js_round(value) for key, value in values.items()},
    }
