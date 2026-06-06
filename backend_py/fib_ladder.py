"""斐波那契逆推价格阶梯(灯区)——【金融逆思维】框架的价位骨架。

注意:这不是标准斐波那契回撤(L + D*ratio,在区间内),而是**逆推/外扩**:
    level = base ± (D / ratio)
把当前区间 D 当成"更大结构的某个 fib 分数",反推完整波幅。等价倍数:
    ratio 0.618 → 1.618×D   ratio 0.500 → 2.0×D   ratio 0.382 → 2.618×D

    上逆推(向上压力位): L + D/ratio
    下逆推(向下支撑位): H - D/ratio

D = H - L。这条价位阶梯用于:挂筹码的价位、量价格延伸到哪档(乖离/极端度)、
设目标与边际线止损。颜色(红/黄/绿)按延伸远近分档。

红线:这是**价位坐标/描述层**,不预测方向、不给买卖建议。
"""

from __future__ import annotations

from typing import Any

# 默认 fib 比例 → 逆推倍数:0.618→1.618, 0.5→2.0, 0.382→2.618
DEFAULT_RATIOS = (0.618, 0.500, 0.382)


def reverse_fib_ladder(high: float, low: float, ratios: tuple[float, ...] = DEFAULT_RATIOS) -> dict[str, Any]:
    """给定区间上下限,返回上/下逆推价位阶梯。"""
    d = high - low
    up = [{"ratio": r, "mult": round(1.0 / r, 4), "price": low + d / r} for r in ratios]
    down = [{"ratio": r, "mult": round(1.0 / r, 4), "price": high - d / r} for r in ratios]
    return {"high": high, "low": low, "range": d, "up": up, "down": down}


def classify_price(price: float, high: float, low: float, ratios: tuple[float, ...] = DEFAULT_RATIOS) -> dict[str, Any]:
    """当前价落在阶梯哪一档:区间内 / 上逆推第几档 / 下逆推第几档,及延伸倍数。"""
    d = high - low
    if low <= price <= high:
        pos = (price - low) / d if d else 0.0
        return {"side": "in_range", "zone": "区间内", "rangePct": round(pos * 100, 2), "extMult": 0.0}
    if price > high:
        ext = (price - low) / d if d else 0.0  # 价距 L 的 D 倍数
        return {"side": "up", "extMult": round(ext, 3), "zone": _zone(ext)}
    ext = (high - price) / d if d else 0.0      # 价距 H 的 D 倍数
    return {"side": "down", "extMult": round(ext, 3), "zone": _zone(ext)}


def _zone(ext_mult: float) -> str:
    """延伸倍数 → 灯区(待用户确认精确阈值/配色)。
    暂定:<1.618 绿(常态)、1.618~2.618 黄(延伸)、>2.618 红(极端)。"""
    if ext_mult < 1.618:
        return "绿"
    if ext_mult < 2.618:
        return "黄"
    return "红"


def _demo() -> None:
    high, low = 97924.49, 80600.00
    lad = reverse_fib_ladder(high, low)
    print(f"H={high}  L={low}  D={lad['range']}")
    print("上逆推(L + D/ratio):")
    for x in lad["up"]:
        print(f"  ratio {x['ratio']:.3f} ({x['mult']}×D) → {x['price']:.2f}")
    print("下逆推(H - D/ratio):")
    for x in lad["down"]:
        print(f"  ratio {x['ratio']:.3f} ({x['mult']}×D) → {x['price']:.2f}")
    for p in (62824, 71000, 108633, 130000):
        print(f"  price {p} → {classify_price(p, high, low)}")


if __name__ == "__main__":
    _demo()
