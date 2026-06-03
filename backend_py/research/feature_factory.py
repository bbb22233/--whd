from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any, Callable, Iterable

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
    from decimal import Decimal, ROUND_HALF_UP

    quant = Decimal(1).scaleb(-digits)
    return float(Decimal(float(value)).quantize(quant, rounding=ROUND_HALF_UP))


def js_sum(values: Iterable[float]) -> float:
    total = 0.0
    for value in values:
        total += value
    return total


def js_number_to_string(value: Any) -> str:
    if not finite(value):
        return str(value)
    number = float(value)
    integer = int(number)
    return str(integer) if number == integer else repr(number)


def average(values: list[float]) -> float:
    return js_sum(values) / len(values) if values else 0


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
        trend_score = js_sum(momentum_values[f"d{period}"] * indicator.trendWeights.get(str(period), 0) for period in indicator.momentumPeriods)
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


def label_tone(label: str) -> str:
    if "下行" in label:
        return "negative"
    if "上行" in label:
        return "positive"
    if any(token in label for token in ["下侧", "冷却", "压缩", "弱势"]):
        return "warning"
    if any(token in label for token in ["上侧", "扩张", "强趋势", "放量"]):
        return "positive"
    return "neutral"


def classify_volatility_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    atr_percentile = snapshot["volatility"]["atrPercentile"]
    multiple_percentile = snapshot["volatility"]["multiplePercentile"]
    candidates = [
        {"state": "波动压缩", "confidence": max(0, ((35 - atr_percentile) / 35) + ((35 - multiple_percentile) / 35)) / 2},
        {"state": "波动启动", "confidence": max(0, ((45 - atr_percentile) / 45) + ((multiple_percentile - 70) / 30)) / 2},
        {"state": "高波动扩张", "confidence": max(0, ((atr_percentile - 65) / 35) + ((multiple_percentile - 65) / 35)) / 2},
        {"state": "高波动冷却", "confidence": max(0, ((atr_percentile - 65) / 35) + ((35 - multiple_percentile) / 35)) / 2},
    ]
    candidates.sort(key=lambda item: item["confidence"], reverse=True)
    if candidates[0]["confidence"] <= 0.05:
        middle_distance = (abs(atr_percentile - 50) + abs(multiple_percentile - 50)) / 100
        return {"state": "常态波动", "confidence": clamp(1 - middle_distance, 0, 1)}
    return {"state": candidates[0]["state"], "confidence": clamp(candidates[0]["confidence"], 0, 1)}


def classify_position_deviation(deviation_atr: float, position_percent: float, prefix: str) -> dict[str, Any]:
    abs_deviation = abs(deviation_atr)
    if abs_deviation <= 0.35:
        return {"label": f"{prefix}贴近", "side": 0, "extremity": "near", "confidence": clamp(1 - (abs_deviation / 0.35), 0, 1)}
    if deviation_atr > 0:
        extreme = position_percent >= 85 or abs_deviation >= 2.5
        return {
            "label": f"{prefix}上侧极端" if extreme else f"{prefix}上侧偏离",
            "side": 1,
            "extremity": "extreme" if extreme else "deviation",
            "confidence": clamp(max((position_percent - 70) / 30, abs_deviation / 4), 0, 1) if extreme else clamp(abs_deviation / 2, 0, 1),
        }
    extreme = position_percent <= 15 or abs_deviation >= 2.5
    return {
        "label": f"{prefix}下侧极端" if extreme else f"{prefix}下侧偏离",
        "side": -1,
        "extremity": "extreme" if extreme else "deviation",
        "confidence": clamp(max((30 - position_percent) / 30, abs_deviation / 4), 0, 1) if extreme else clamp(abs_deviation / 2, 0, 1),
    }


def classify_trend(snapshot: dict[str, Any], config: ResearchConfig) -> dict[str, Any]:
    resonance_direction = snapshot["momentum"]["resonanceDirection"]
    resonance_count = snapshot["momentum"]["resonanceCount"]
    trend_score = snapshot["momentum"]["trendScore"]
    abs_trend = abs(trend_score)
    thresholds = config.thresholds
    if resonance_count >= 3 and abs_trend >= thresholds.strongTrendPct and resonance_direction != "mixed":
        return {
            "label": "强趋势上行" if resonance_direction == "up" else "强趋势下行",
            "direction": resonance_direction,
            "strength": "strong",
            "confidence": clamp((abs_trend / (thresholds.strongTrendPct * 2)) + (resonance_count / 8), 0, 1),
        }
    if resonance_count >= 2 and abs_trend >= thresholds.weakTrendPct:
        return {
            "label": "弱趋势上行" if resonance_direction == "up" else "弱趋势下行" if resonance_direction == "down" else "弱趋势混合",
            "direction": resonance_direction,
            "strength": "weak",
            "confidence": clamp((abs_trend / (thresholds.strongTrendPct * 2)) + (resonance_count / 10), 0, 0.75),
        }
    return {"label": "趋势不明", "direction": "mixed", "strength": "none", "confidence": clamp(1 - (abs_trend / thresholds.strongTrendPct), 0, 1)}


def classify_volume(snapshot: dict[str, Any], config: ResearchConfig) -> dict[str, Any]:
    multiple = snapshot["volume"]["multiple"]
    if multiple >= config.thresholds.volumeExpansion:
        return {"label": "放量", "confidence": clamp((multiple - config.thresholds.volumeExpansion) / config.thresholds.volumeExpansion, 0.35, 1)}
    if multiple <= 0.75:
        return {"label": "缩量", "confidence": clamp((0.75 - multiple) / 0.75, 0.25, 1)}
    return {"label": "量能正常", "confidence": clamp(1 - abs(multiple - 1), 0, 1)}


def classify_energy(snapshot: dict[str, Any]) -> dict[str, Any]:
    remaining = snapshot["volatility"]["remainingMomentumAtr"]
    if remaining >= 0.2:
        return {"label": "振幅已超ATR", "confidence": clamp(remaining / 1.2, 0.25, 1)}
    if remaining <= -0.2:
        return {"label": "振幅未满ATR", "confidence": clamp(abs(remaining) / 1.2, 0.25, 1)}
    return {"label": "接近一倍ATR", "confidence": clamp(1 - abs(remaining) / 0.2, 0, 1)}


def classify_atr_slope(snapshot: dict[str, Any]) -> dict[str, Any]:
    atr3_to_21 = snapshot["volatility"]["fibAtrComparisons"]["atr3To21"]
    atr8_to_21 = snapshot["volatility"]["fibAtrComparisons"]["atr8To21"]
    if atr3_to_21 >= 1.08 and atr8_to_21 >= 1:
        return {"label": "短波动升温", "confidence": clamp(((atr3_to_21 - 1) + max(0, atr8_to_21 - 1)) / 0.35, 0.25, 1)}
    if atr3_to_21 <= 0.88 and atr8_to_21 <= 0.96:
        return {"label": "短波动降温", "confidence": clamp(((1 - atr3_to_21) + max(0, 1 - atr8_to_21)) / 0.35, 0.25, 1)}
    return {"label": "短波动中性", "confidence": clamp(1 - abs(atr3_to_21 - 1), 0, 1)}


def build_weather_labels(snapshot: dict[str, Any], config: ResearchConfig) -> list[dict[str, Any]]:
    volatility = classify_volatility_state(snapshot)
    middle = classify_position_deviation(snapshot["position"]["middleDeviationAtr"], snapshot["position"]["middlePositionPct"], "中值")
    ma = classify_position_deviation(snapshot["position"]["maDeviationAtr"], snapshot["position"]["maPositionPct"], "MA")
    trend = classify_trend(snapshot, config)
    volume = classify_volume(snapshot, config)
    energy = classify_energy(snapshot)
    atr_slope = classify_atr_slope(snapshot)
    return [
        {"dimension": "波动", "label": volatility["state"], "confidence": volatility["confidence"], "tone": label_tone(volatility["state"])},
        {"dimension": "短波动", "label": atr_slope["label"], "confidence": atr_slope["confidence"], "tone": label_tone(atr_slope["label"])},
        {
            "dimension": "中值位置",
            "label": middle["label"],
            "confidence": middle["confidence"],
            "tone": label_tone(middle["label"]),
            "side": middle["side"],
            "extremity": middle["extremity"],
        },
        {
            "dimension": "MA位置",
            "label": ma["label"],
            "confidence": ma["confidence"],
            "tone": label_tone(ma["label"]),
            "side": ma["side"],
            "extremity": ma["extremity"],
        },
        {
            "dimension": "趋势",
            "label": trend["label"],
            "confidence": trend["confidence"],
            "tone": label_tone(trend["label"]),
            "direction": trend["direction"],
            "strength": trend["strength"],
        },
        {"dimension": "量能", "label": volume["label"], "confidence": volume["confidence"], "tone": label_tone(volume["label"])},
        {"dimension": "动能", "label": energy["label"], "confidence": energy["confidence"], "tone": label_tone(energy["label"])},
    ]


def label_by_dimension(labels: list[dict[str, Any]], dimension: str) -> dict[str, Any] | None:
    return next((label for label in labels if label["dimension"] == dimension), None)


def weather_name(labels: list[dict[str, Any]]) -> str:
    volatility = (label_by_dimension(labels, "波动") or {}).get("label", "未知波动")
    trend = (label_by_dimension(labels, "趋势") or {}).get("label", "趋势未知")
    middle = (label_by_dimension(labels, "中值位置") or {}).get("label", "中值未知")
    ma = (label_by_dimension(labels, "MA位置") or {}).get("label", "MA未知")
    return f"{volatility} / {trend} / {middle} / {ma}"


def score_reason(label: str, condition: bool) -> str | None:
    return label if condition else None


def route(key: str, label: str, family: str, direction: str, score: float, reasons: list[str | None]) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "family": family,
        "direction": direction,
        "score": js_round(clamp(score, 0, 100), 2),
        "reasons": [reason for reason in reasons if reason],
    }


def route_strategies(snapshot: dict[str, Any], labels: list[dict[str, Any]]) -> dict[str, Any]:
    volatility_label = (label_by_dimension(labels, "波动") or {}).get("label", "")
    middle_label = (label_by_dimension(labels, "中值位置") or {}).get("label", "")
    ma_label = (label_by_dimension(labels, "MA位置") or {}).get("label", "")
    volume_label = (label_by_dimension(labels, "量能") or {}).get("label", "")
    energy_label = (label_by_dimension(labels, "动能") or {}).get("label", "")
    short_vol_label = (label_by_dimension(labels, "短波动") or {}).get("label", "")
    trend_score = snapshot["momentum"]["trendScore"]
    abs_trend = abs(trend_score)
    resonance_count = snapshot["momentum"]["resonanceCount"]
    trend_direction = snapshot["momentum"]["resonanceDirection"]
    middle_deviation = snapshot["position"]["middleDeviationAtr"]
    ma_deviation = snapshot["position"]["maDeviationAtr"]
    middle_abs = abs(middle_deviation)
    volume_multiple = snapshot["volume"]["multiple"]
    atr_percentile = snapshot["volatility"]["atrPercentile"]
    multiple_percentile = snapshot["volatility"]["multiplePercentile"]
    volatility_multiple = snapshot["volatility"]["multiple"]
    atr3_to_21 = snapshot["volatility"]["fibAtrComparisons"]["atr3To21"]
    atr8_to_21 = snapshot["volatility"]["fibAtrComparisons"]["atr8To21"]
    compressed = volatility_label == "波动压缩"
    high_expansion = volatility_label == "高波动扩张"
    high_cooling = volatility_label == "高波动冷却"
    short_heating = short_vol_label == "短波动升温" or (atr3_to_21 >= 1.08 and atr8_to_21 >= 1)
    short_cooling = short_vol_label == "短波动降温" or (atr3_to_21 <= 0.88 and atr8_to_21 <= 0.96)
    strong_up = trend_direction == "up" and trend_score > 0 and resonance_count >= 3
    strong_down = trend_direction == "down" and trend_score < 0 and resonance_count >= 3
    middle_upper_extreme = "上侧极端" in middle_label
    middle_lower_extreme = "下侧极端" in middle_label
    middle_upper = middle_deviation > 0.35
    middle_lower = middle_deviation < -0.35
    ma_upper_extreme = "上侧极端" in ma_label
    ma_lower_extreme = "下侧极端" in ma_label
    low_trend = abs_trend < 1.2
    normal_volume = volume_multiple >= 0.75 and volume_multiple <= 1.2

    trend_base = 12 + (resonance_count * 10) + min(abs_trend * 5, 32) + (8 if volume_multiple >= 1.15 else 0)
    trend_long = trend_base + (22 if strong_up else 0) - (38 if strong_down else 0) - (8 if compressed else 0) - (10 if middle_upper_extreme else 0) - (14 if ma_lower_extreme else 0)
    trend_short = trend_base + (22 if strong_down else 0) - (38 if strong_up else 0) - (24 if compressed else 0) - (14 if short_cooling else 0) - (12 if middle_lower_extreme else 0) - (10 if ma_lower_extreme else 0) - (14 if ma_upper_extreme else 0)
    breakout_base = (
        18
        + (16 if compressed else 0)
        + (24 if short_heating else 0)
        + (20 if multiple_percentile >= 70 else 0)
        + (10 if volume_multiple >= 1.2 else 0)
        - (12 if short_cooling else 0)
        - (16 if high_cooling else 0)
    )
    breakout_up = breakout_base + (18 if strong_up else 0) - (12 if strong_down else 0) + (8 if ma_deviation > 0 else -8) + (5 if middle_deviation > 0 else -5)
    breakout_down = breakout_base + (18 if strong_down else 0) - (12 if strong_up else 0) + (8 if ma_deviation < 0 else -8) + (5 if middle_deviation < 0 else -5)
    reversion_base = 12 + clamp((middle_abs - 0.75) * 18, 0, 34) + (8 if compressed or short_cooling else 0) - (8 if high_expansion else 0)
    mean_reversion_long = reversion_base + (24 if middle_lower else -18) + (18 if middle_lower_extreme else 0) + (8 if ma_lower_extreme else 0) - (12 if strong_down else 0)
    mean_reversion_short = reversion_base + (24 if middle_upper else -18) + (18 if middle_upper_extreme else 0) + (8 if ma_upper_extreme else 0) - (12 if strong_up else 0)
    grid_neutral = (
        38
        + (16 if atr_percentile <= 40 else 0)
        + (14 if volatility_multiple <= 1 else 0)
        + (22 if low_trend else 0)
        + (8 if normal_volume else 0)
        - (30 if high_expansion else 0)
        - (24 if abs_trend >= 3 else 0)
        - (18 if middle_abs >= 1.3 else 0)
        - (8 if ma_upper_extreme or ma_lower_extreme else 0)
    )
    max_directional = max(trend_long, trend_short, breakout_up, breakout_down, mean_reversion_long, mean_reversion_short, grid_neutral)
    wait_defense = (
        34
        + (10 if compressed else 0)
        + (10 if short_cooling else 0)
        + (14 if ma_lower_extreme or ma_upper_extreme else 0)
        + (6 if energy_label == "振幅未满ATR" else 0)
        + (6 if volume_label == "缩量" else 0)
        + (18 if max_directional < 45 else 0)
        - (max_directional * 0.14)
    )
    routes = [
        route("trendLong", "趋势追多", "trend", "long", trend_long, [score_reason("多周期趋势向上", strong_up), score_reason("趋势向下，追多降权", strong_down), score_reason("低波动压缩，趋势入场降权", compressed), score_reason("价格在MA下侧极端，追多需等待修复", ma_lower_extreme)]),
        route("trendShort", "趋势做空", "trend", "short", trend_short, [score_reason("多周期趋势向下", strong_down), score_reason("趋势向上，追空降权", strong_up), score_reason("低波动压缩，直接追空降权", compressed), score_reason("短波动降温，直接追空降权", short_cooling), score_reason("价格在MA上侧极端，追空需等待转弱", ma_upper_extreme)]),
        route("breakoutUp", "向上突破", "breakout", "long", breakout_up, [score_reason("波动压缩，具备等待突破结构", compressed), score_reason("短周期ATR升温", short_heating), score_reason("放量或量能偏强", volume_multiple >= 1.2), score_reason("趋势下行，上破降权", strong_down)]),
        route("breakoutDown", "向下突破", "breakout", "short", breakout_down, [score_reason("波动压缩，具备等待突破结构", compressed), score_reason("短周期ATR升温", short_heating), score_reason("放量或量能偏强", volume_multiple >= 1.2), score_reason("趋势下行，下破顺势加权", strong_down)]),
        route("meanReversionLong", "低吸均值回归", "meanReversion", "long", mean_reversion_long, [score_reason("中值下侧偏离", middle_lower), score_reason("中值下侧极端", middle_lower_extreme), score_reason("短波动降温，回归环境加权", short_cooling), score_reason("趋势强下行，低吸降权", strong_down)]),
        route("meanReversionShort", "高抛均值回归", "meanReversion", "short", mean_reversion_short, [score_reason("中值上侧偏离", middle_upper), score_reason("中值上侧极端", middle_upper_extreme), score_reason("短波动降温，回归环境加权", short_cooling), score_reason("趋势强上行，高抛降权", strong_up)]),
        route("gridNeutral", "震荡网格", "grid", "neutral", grid_neutral, [score_reason("ATR处于低位", atr_percentile <= 40), score_reason("当日振幅未超过ATR", volatility_multiple <= 1), score_reason("趋势动能弱", low_trend), score_reason("趋势动能强，网格降权", abs_trend >= 3)]),
        route("waitDefense", "防守等待", "wait", "neutral", wait_defense, [score_reason("波动压缩，等待确认", compressed), score_reason("短波动降温", short_cooling), score_reason("MA位置极端，等待结构修复", ma_lower_extreme or ma_upper_extreme), score_reason("振幅未满ATR", energy_label == "振幅未满ATR")]),
    ]
    routes.sort(key=lambda item: item["score"], reverse=True)
    score_map = {item["key"]: item["score"] for item in routes}
    scores = {
        **score_map,
        "trendFollowing": js_round(max(score_map["trendLong"], score_map["trendShort"]), 2),
        "breakout": js_round(max(score_map["breakoutUp"], score_map["breakoutDown"]), 2),
        "meanReversion": js_round(max(score_map["meanReversionLong"], score_map["meanReversionShort"]), 2),
        "grid": score_map["gridNeutral"],
        "wait": score_map["waitDefense"],
    }
    return {"scores": scores, "routes": routes, "topRoutes": routes[:3]}


def build_feature_factory_core(clean_payload: dict[str, Any], config: ResearchConfig) -> dict[str, Any]:
    bundle = build_feature_factory_dataset(clean_payload, config)
    snapshots = bundle["snapshots"]
    dataset = bundle["dataset"]
    feature_rows = []
    for row in dataset["rows"]:
        labels = build_weather_labels(row["snapshot"], config)
        route_result = route_strategies(row["snapshot"], labels)
        feature_rows.append({"row": row, "labels": labels, "routeResult": route_result, "strategyScores": route_result["scores"]})
    latest = feature_rows[-1] if feature_rows else None
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
        },
        "features": dataset["features"],
        "featureStats": dataset["stats"],
        "current": {
            "date": latest["row"]["snapshot"]["date"],
            "close": js_round(latest["row"]["snapshot"]["price"]["last"], 2),
            "weatherName": weather_name(latest["labels"]),
            "weatherConfidencePct": js_round(average([label["confidence"] for label in latest["labels"]]) * 100, 2),
            "labels": [{**label, "confidencePct": js_round(label["confidence"] * 100, 2)} for label in latest["labels"]],
            "strategyScores": latest["strategyScores"],
            "topRoutes": latest["routeResult"]["topRoutes"],
            "strategyRoutes": latest["routeResult"]["routes"],
            "values": {key: js_round(value) for key, value in latest["row"]["values"].items()},
        }
        if latest
        else None,
        "featureRows": [feature_csv_row(item) for item in feature_rows],
    }


def feature_csv_row(item: dict[str, Any]) -> dict[str, Any]:
    row = item["row"]
    snapshot = row["snapshot"]
    values = row["values"]
    labels = item["labels"]
    strategy_scores = item["strategyScores"]
    route_result = item["routeResult"]
    return {
        "date": snapshot["date"],
        "close": js_round(snapshot["price"]["last"], 2),
        "weatherName": weather_name(labels),
        "weatherConfidencePct": js_round(average([label["confidence"] for label in labels]) * 100, 2),
        "weatherLabels": " | ".join(f"{label['dimension']}:{label['label']}" for label in labels),
        "topRoutes": " | ".join(f"{route['label']}:{route['score']}" for route in route_result["topRoutes"]),
        "trendLongScore": strategy_scores["trendLong"],
        "trendShortScore": strategy_scores["trendShort"],
        "breakoutUpScore": strategy_scores["breakoutUp"],
        "breakoutDownScore": strategy_scores["breakoutDown"],
        "meanReversionLongScore": strategy_scores["meanReversionLong"],
        "meanReversionShortScore": strategy_scores["meanReversionShort"],
        "gridNeutralScore": strategy_scores["gridNeutral"],
        "waitDefenseScore": strategy_scores["waitDefense"],
        "trendFollowingScore": strategy_scores["trendFollowing"],
        "breakoutScore": strategy_scores["breakout"],
        "meanReversionScore": strategy_scores["meanReversion"],
        "gridScore": strategy_scores["grid"],
        "waitScore": strategy_scores["wait"],
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
    }
