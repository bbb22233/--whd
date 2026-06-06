"""分型(顶/底分型)检测 → 定出逆推灯区的 H/L。

分型(缠论式 3 根K线):
    顶分型:中间K线 high 高于左右、且 low 也高于左右(局部顶)。
    底分型:中间K线 low 低于左右、且 high 也低于左右(局部底)。
width>1 时要求比左右各 width 根都极端(更强、更少的分型)。

防偷看:第 i 根的分型要等到第 i+width 根出现才确认,用的是已收盘K线。
"current" 取**最近确认的顶分型 high = H、最近确认的底分型 low = L**,喂给逆推阶梯。

可调:width(分型强度);是否做缠论"包含关系处理"/笔级过滤(默认不做,用原始 3 根分型)。
红线:只产描述性价位坐标,不预测方向、不给买卖建议。
"""

from __future__ import annotations

from typing import Any

from .fib_ladder import classify_price, reverse_fib_ladder


def find_fractals(candles: list[dict[str, Any]], width: int = 1) -> tuple[list[int], list[int]]:
    """返回 (顶分型下标列表, 底分型下标列表)。candles 需含 high/low。"""
    tops: list[int] = []
    bottoms: list[int] = []
    n = len(candles)
    for i in range(width, n - width):
        h, l = candles[i]["high"], candles[i]["low"]
        neigh = range(1, width + 1)
        is_top = all(h > candles[i - j]["high"] and h > candles[i + j]["high"] for j in neigh) and \
                 all(l > candles[i - j]["low"] and l > candles[i + j]["low"] for j in neigh)
        is_bot = all(l < candles[i - j]["low"] and l < candles[i + j]["low"] for j in neigh) and \
                 all(h < candles[i - j]["high"] and h < candles[i + j]["high"] for j in neigh)
        if is_top:
            tops.append(i)
        if is_bot:
            bottoms.append(i)
    return tops, bottoms


def latest_fractal_range(candles: list[dict[str, Any]], width: int = 1) -> dict[str, Any] | None:
    """最近确认的 顶分型 high=H、底分型 low=L。不足则 None。"""
    tops, bottoms = find_fractals(candles, width)
    if not tops or not bottoms:
        return None
    ti, bi = tops[-1], bottoms[-1]
    return {
        "high": candles[ti]["high"], "low": candles[bi]["low"],
        "topIdx": ti, "botIdx": bi,
        "topDate": candles[ti].get("date"), "botDate": candles[bi].get("date"),
    }


def ladder_from_fractals(candles: list[dict[str, Any]], width: int = 1) -> dict[str, Any] | None:
    """分型定 H/L → 逆推灯区 + 当前收盘价落档。"""
    rng = latest_fractal_range(candles, width)
    if not rng:
        return None
    ladder = reverse_fib_ladder(rng["high"], rng["low"])
    price = candles[-1]["close"]
    return {
        "fractalRange": rng,
        "ladder": ladder,
        "currentPrice": price,
        "currentZone": classify_price(price, rng["high"], rng["low"]),
    }


if __name__ == "__main__":  # 离线 demo:读冻结 fixture 跑一遍
    import json
    import sys
    from pathlib import Path

    path = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/data/clean/BTC_USDT_1D_clean.json"
    candles = json.loads(Path(path).read_text(encoding="utf-8"))["candles"]
    width = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    res = ladder_from_fractals(candles, width=width)
    print(json.dumps(res, ensure_ascii=False, indent=2))
