"""进场位置优化(筹码怎么打)—— 把结构地图变成一张"进场计划表"。

默认规则(都可调):
- 候选进场位 = 密集 S-R(埋伏在硬位);仓量按 S-R 强度(测试次数)分配 —— 越硬放越多。
- 固定最大风险:给定 risk_budget(最多亏总资金的百分之几),反推总仓量 → 风险预先锁死。
- 止损 = 箱子另一边(边际线);止盈 = 逆推台阶(或箱子对边)。
- 输出:每档价位+仓量、加权均价、总仓、最大风险、止损位、止盈位、盈亏比 R:R。

direction:
- long  = 在下方支撑埋伏买、涨到上方止盈(震荡/向上突破)
- short = 在上方阻力埋伏卖、跌到下方止盈(向下突破)
- auto  = 按真假突破状态自动选(confirmed_up→long, confirmed_down→short, 其余→long 默认演示)

红线:这是**描述性的"计划/位置"**,不预测方向、不替你下单。要不要进、进多少,是你的决定。
"""

from __future__ import annotations

from typing import Any

from .fib_ladder import reverse_fib_ladder


def _pick_direction(structure: dict[str, Any]) -> str:
    st = (structure.get("breakout") or {}).get("state", "")
    if st in ("confirmed_up", "pending_up", "fakeout_down"):
        return "long"
    if st in ("confirmed_down", "pending_down", "fakeout_up"):
        return "short"
    return "long"  # inside:默认震荡做多埋伏(也可手动传 short)


def build_entry_plan(structure: dict[str, Any], risk_budget: float = 0.02,
                     max_levels: int = 3, direction: str = "auto",
                     buffer_pct: float = 0.05) -> dict[str, Any] | None:
    """structure = analyze_structure(...) 的返回。risk_budget = 最大可亏(占总资金比例)。"""
    piv = structure.get("latestPivot")
    if not piv:
        return None
    price = structure["price"]
    hi, lo = piv["high"], piv["low"]
    buf = buffer_pct * (hi - lo)
    side = _pick_direction(structure) if direction == "auto" else direction
    clusters = structure.get("srClusters") or []
    ladder = reverse_fib_ladder(hi, lo)

    if side == "long":
        # 在现价下方的密集支撑埋伏买;止损放最低进场档(或箱底)再往下;止盈箱顶 / 上逆推
        cands = sorted([c for c in clusters if c["price"] < price], key=lambda c: -c["price"])[:max_levels]
        tp = max(hi, ladder["up"][0]["price"])
    else:
        # 在现价上方的密集阻力埋伏卖;止损放最高进场档(或箱顶)再往上;止盈箱底 / 下逆推
        cands = sorted([c for c in clusters if c["price"] > price], key=lambda c: c["price"])[:max_levels]
        tp = min(lo, ladder["down"][0]["price"])

    if not cands:
        return {"direction": side, "note": "当前方向没有可埋伏的密集 S-R(可放宽 sr_tol 或换方向)"}

    entry_prices = [c["price"] for c in cands]
    if side == "long":
        stop = min(min(entry_prices), lo) - buf   # 止损真在所有进场档之下
    else:
        stop = max(max(entry_prices), hi) + buf   # 止损真在所有进场档之上

    # 按 S-R 强度(count)分配权重
    total_w = sum(c["count"] for c in cands)
    legs = [{"price": round(c["price"], 2), "weight": round(c["count"] / total_w, 3),
             "srCount": c["count"]} for c in cands]
    avg_cost = sum(l["price"] * l["weight"] for l in legs)

    # 固定最大风险 → 反推总仓量(stop 打到时正好亏 risk_budget)
    risk_dist = abs(avg_cost - stop) / avg_cost  # 均价到止损的距离(比例)
    total_stake_pct = risk_budget / risk_dist if risk_dist > 0 else 0.0  # 总仓占资金比例
    for l in legs:
        l["stakePct"] = round(total_stake_pct * l["weight"] * 100, 2)  # 每档占资金 %

    reward_dist = abs(tp - avg_cost) / avg_cost
    rr = reward_dist / risk_dist if risk_dist > 0 else 0.0

    return {
        "direction": side,
        "legs": legs,                                   # 每档:价位 / 权重 / 仓量% / S-R强度
        "avgCost": round(avg_cost, 2),
        "totalStakePct": round(total_stake_pct * 100, 2),   # 总仓占资金 %
        "stop": round(stop, 2),
        "tp": round(tp, 2),
        "maxRiskPct": round(risk_budget * 100, 2),          # 最大亏(锁死)
        "riskRewardRR": round(rr, 2),                       # 盈亏比
        "box": {"low": round(lo, 2), "high": round(hi, 2)},
    }


if __name__ == "__main__":
    import json
    import sys
    from pathlib import Path

    from .structure import analyze_structure

    path = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/data/clean/BTC_USDT_1D_clean.json"
    candles = json.loads(Path(path).read_text(encoding="utf-8"))["candles"]
    s = analyze_structure(candles)
    plan = build_entry_plan(s, risk_budget=0.02, max_levels=3, direction="long")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
