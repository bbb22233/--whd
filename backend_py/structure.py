"""结构层:中枢(大框)+ 密集支撑阻力 —— 框架式运动的"箱子"与硬位。

接 fractal 的笔(strokes):
- 中枢(B/缠论):≥3 笔连续重叠的价格带 = 大箱子(价格反复在里面晃的核心区)。
  zoneHigh = 这些笔高点的最小值;zoneLow = 这些笔低点的最大值(重叠区)。
  high/low = 这段所有笔的最高/最低(箱子整体范围)。
- 密集支撑阻力:把所有笔的高低点按价位聚堆,堆得越多的价格带 = 越硬的 S/R。
- 突破后用"被突破的那个箱子"算逆推台阶(空间随箱子大小放大)。

红线:只产描述性结构/价位,不预测方向、不给买卖建议。
"""

from __future__ import annotations

from typing import Any

from .fractal import build_strokes


def stroke_ranges(strokes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """相邻端点 → 每一笔的价格区间。"""
    out = []
    for i in range(len(strokes) - 1):
        a, b = strokes[i], strokes[i + 1]
        out.append({"low": min(a["price"], b["price"]), "high": max(a["price"], b["price"]),
                    "i0": a["idx"], "i1": b["idx"]})
    return out


def find_pivots(strokes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """中枢:≥3 笔连续重叠的箱子。返回 [{zoneHigh,zoneLow,high,low,startIdx,endIdx,strokes}]。"""
    rngs = stroke_ranges(strokes)
    pivots: list[dict[str, Any]] = []
    i = 0
    while i + 2 < len(rngs):
        zg = min(rngs[i]["high"], rngs[i + 1]["high"], rngs[i + 2]["high"])
        zd = max(rngs[i]["low"], rngs[i + 1]["low"], rngs[i + 2]["low"])
        if zd < zg:  # 三笔有重叠 → 成中枢
            j = i + 3
            while j < len(rngs):
                nzg, nzd = min(zg, rngs[j]["high"]), max(zd, rngs[j]["low"])
                if nzd < nzg:
                    zg, zd, j = nzg, nzd, j + 1
                else:
                    break
            seg = rngs[i:j]
            pivots.append({
                "zoneHigh": zg, "zoneLow": zd,
                "high": max(r["high"] for r in seg), "low": min(r["low"] for r in seg),
                "startIdx": seg[0]["i0"], "endIdx": seg[-1]["i1"], "strokeCount": len(seg),
            })
            i = j
        else:
            i += 1
    return pivots


def cluster_levels(strokes: list[dict[str, Any]], tol: float = 0.015) -> list[dict[str, Any]]:
    """密集支撑阻力:把笔的高低点按价位(相对距离 ≤tol)聚堆,count 越大越硬。"""
    prices = sorted(e["price"] for e in strokes)
    clusters: list[list[float]] = []
    for p in prices:
        if clusters and abs(p - (sum(clusters[-1]) / len(clusters[-1]))) / p <= tol:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    out = [{"price": sum(c) / len(c), "count": len(c), "lo": min(c), "hi": max(c)} for c in clusters]
    return sorted(out, key=lambda x: x["count"], reverse=True)


def classify_breakout(candles: list[dict[str, Any]], pivot: dict[str, Any],
                      confirm_bars: int = 2, buffer_pct: float = 0.05) -> dict[str, Any]:
    """真假突破判定(默认规则,可调):
    - 在箱子里 → inside(震荡/埋伏模式)。
    - 收盘越过箱边 + 缓冲,且连续 ≥confirm_bars 根站稳 → confirmed(真突破)。
    - 越过箱边但还没站稳 → pending(待确认,可能假)。
    - 近期越过又缩回箱内 → fakeout(假突破)。
    buffer = buffer_pct × 箱高,防止贴边毛刺误判。
    """
    hi, lo = pivot["high"], pivot["low"]
    buf = buffer_pct * (hi - lo)
    recent = candles[-(confirm_bars + 3):]
    closes = [c["close"] for c in recent]
    last = closes[-1]

    def consec_beyond(edge: float, up: bool) -> int:
        n = 0
        for c in reversed(closes):
            if (up and c > edge) or (not up and c < edge):
                n += 1
            else:
                break
        return n

    if last > hi + buf:
        held = consec_beyond(hi, True)
        return {"state": "confirmed_up" if held >= confirm_bars else "pending_up",
                "side": "up", "heldBars": held, "edge": hi}
    if last < lo - buf:
        held = consec_beyond(lo, False)
        return {"state": "confirmed_down" if held >= confirm_bars else "pending_down",
                "side": "down", "heldBars": held, "edge": lo}
    # 现价在箱内:看近期有没有"冲出又缩回"= 假突破
    poked_up = any(c["high"] > hi + buf for c in recent[:-1])
    poked_dn = any(c["low"] < lo - buf for c in recent[:-1])
    if poked_up and last <= hi:
        return {"state": "fakeout_up", "side": "up", "edge": hi}
    if poked_dn and last >= lo:
        return {"state": "fakeout_down", "side": "down", "edge": lo}
    return {"state": "inside", "side": "range", "edge": None}


def analyze_structure(candles: list[dict[str, Any]], width: int = 2, min_gap: int = 4,
                      sr_tol: float = 0.015, sr_lookback: int = 40) -> dict[str, Any] | None:
    strokes = build_strokes(candles, width, min_gap)
    if len(strokes) < 4:
        return None
    pivots = find_pivots(strokes)
    # 密集 S/R 只用近期的笔(远古价位不构成当前支撑阻力)
    clusters = cluster_levels(strokes[-sr_lookback:], sr_tol)
    price = candles[-1]["close"]
    latest = pivots[-1] if pivots else None
    breakout = classify_breakout(candles, latest) if latest else None
    return {
        "strokes": strokes, "pivots": pivots, "srClusters": clusters,
        "latestPivot": latest, "price": price, "breakout": breakout,
    }


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    path = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/data/clean/BTC_USDT_1D_clean.json"
    candles = json.loads(Path(path).read_text(encoding="utf-8"))["candles"]
    r = analyze_structure(candles)
    print("中枢数:", len(r["pivots"]), "| 现价:", r["price"], "| 突破判定:", r["breakout"]["state"])
    if r["latestPivot"]:
        p = r["latestPivot"]
        print("最近中枢: zone", round(p["zoneLow"]), "-", round(p["zoneHigh"]),
              "| 范围", round(p["low"]), "-", round(p["high"]), "| 含", p["strokeCount"], "笔")
    print("最硬 S/R(前5):", [(round(c["price"]), c["count"]) for c in r["srClusters"][:5]])
