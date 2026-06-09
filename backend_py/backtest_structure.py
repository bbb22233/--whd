"""分析框架回测 v1(诚实、防偷看)——这套"结构→真假突破→逆推止盈"过去赚不赚?

简化版(先回答"核心思路有没有 edge",不是完整筹码网格):
- 逐根走(causal):第 t 根只用 ≤t 的数据算结构(笔/中枢/真假突破)。
- 信号:突破状态**刚变成 confirmed_up/down** → 顺突破方向开一仓(市价≈收盘价)。
- 止损 = 箱子另一边(边际线);止盈 = 第一个逆推台阶。
- 出场:之后任意一根 high/low 触及止损或止盈即平(同根都触按"先止损"保守处理);超 max_hold 根强平。
- 含成本:每边 fee_pct + slippage_pct。单仓、满仓名义,统计 per-trade 收益。

输出:交易数 / 胜率 / 平均盈亏 / 盈亏比 / 总收益 / 最大回撤 / 盈利因子。
红线:这是**验证用回测**,不是买卖建议;结论可能是"不赚"——那也是诚实的、省钱的答案。

用法:
    python -m backend_py.backtest_structure                       # 默认 BTC 1D fixture
    python -m backend_py.backtest_structure <clean.json> [warmup] [fee_bps]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .fib_ladder import reverse_fib_ladder
from .structure import analyze_structure


def _first_tp(structure: dict[str, Any], side: str) -> float | None:
    piv = structure.get("latestPivot")
    if not piv:
        return None
    lad = reverse_fib_ladder(piv["high"], piv["low"])
    return lad["up"][0]["price"] if side == "long" else lad["down"][0]["price"]


def backtest(candles: list[dict[str, Any]], warmup: int = 250, fee_bps: float = 5.0,
             slip_bps: float = 5.0, max_hold: int = 60, buffer_pct: float = 0.05,
             risk_budget: float | None = None, max_leverage: float = 3.0) -> dict[str, Any]:
    """risk_budget=None → 裸打满仓(v1);risk_budget=0.02 → 每笔固定赌 2% 风险(v2,仓位按止损距离反推)。"""
    cost = (fee_bps + slip_bps) / 10000.0  # 单边成本(比例)
    trades: list[dict[str, Any]] = []
    open_pos: dict[str, Any] | None = None
    prev_state = ""

    for t in range(warmup, len(candles)):
        bar = candles[t]
        # 先处理已有持仓:看这根有没有触及止损/止盈
        if open_pos:
            p = open_pos
            hit = None
            if p["side"] == "long":
                if bar["low"] <= p["stop"]:
                    hit = ("stop", p["stop"])
                elif bar["high"] >= p["tp"]:
                    hit = ("tp", p["tp"])
            else:
                if bar["high"] >= p["stop"]:
                    hit = ("stop", p["stop"])
                elif bar["low"] <= p["tp"]:
                    hit = ("tp", p["tp"])
            if hit is None and t - p["entryIdx"] >= max_hold:
                hit = ("timeout", bar["close"])
            if hit:
                reason, exit_px = hit
                d = 1 if p["side"] == "long" else -1
                gross = (exit_px / p["entry"] - 1) * d
                net = gross - 2 * cost  # 进+出两边成本
                trades.append({"side": p["side"], "entry": p["entry"], "exit": round(exit_px, 2),
                               "stop": p["stop"], "reason": reason, "ret": net, "bars": t - p["entryIdx"]})
                open_pos = None

        # 没有持仓时:看突破信号(状态刚变 confirmed)
        if open_pos is None:
            s = analyze_structure(candles[: t + 1])
            st = (s.get("breakout") or {}).get("state", "") if s else ""
            if st in ("confirmed_up", "confirmed_down") and st != prev_state:
                side = "long" if st == "confirmed_up" else "short"
                piv = s["latestPivot"]
                buf = buffer_pct * (piv["high"] - piv["low"])
                tp = _first_tp(s, side)
                stop = (piv["low"] - buf) if side == "long" else (piv["high"] + buf)
                entry = bar["close"]
                # 合理性检查:long 时 tp>entry>stop;short 反之
                ok = (side == "long" and tp > entry > stop) or (side == "short" and tp < entry < stop)
                if ok:
                    open_pos = {"side": side, "entry": entry, "stop": stop, "tp": tp, "entryIdx": t}
            prev_state = st if st else prev_state

    return _stats(trades, risk_budget, max_leverage)


def _stats(trades: list[dict[str, Any]], risk_budget: float | None = None,
           max_leverage: float = 3.0) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {"trades": 0, "note": "没有触发任何交易"}
    rets = [t["ret"] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    # 复利净值 + 最大回撤。固定风险时:仓位 = risk_budget / 止损距离(上限 max_leverage)
    eq = 1.0
    peak = 1.0
    maxdd = 0.0
    for tr in trades:
        r = tr["ret"]
        if risk_budget:
            stop_dist = abs(tr["entry"] - tr["stop"]) / tr["entry"]
            f = min(max_leverage, risk_budget / stop_dist) if stop_dist > 0 else 0.0
            eq *= (1 + f * r)
        else:
            eq *= (1 + r)
        peak = max(peak, eq)
        maxdd = max(maxdd, (peak - eq) / peak)
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    return {
        "trades": n,
        "winRatePct": round(100 * len(wins) / n, 1),
        "avgRetPct": round(100 * sum(rets) / n, 3),
        "avgWinPct": round(100 * (sum(wins) / len(wins)) if wins else 0, 3),
        "avgLossPct": round(100 * (sum(losses) / len(losses)) if losses else 0, 3),
        "profitFactor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "totalReturnPct": round(100 * (eq - 1), 1),
        "maxDrawdownPct": round(100 * maxdd, 1),
        "byReason": {k: sum(1 for t in trades if t["reason"] == k) for k in ("tp", "stop", "timeout")},
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/data/clean/BTC_USDT_1D_clean.json"
    warmup = int(sys.argv[2]) if len(sys.argv) > 2 else 250
    fee = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
    candles = json.loads(Path(path).read_text(encoding="utf-8"))["candles"]
    print(f"# 回测 {Path(path).name}  bars={len(candles)}  warmup={warmup}  fee={fee}bps/边")
    print(json.dumps(backtest(candles, warmup=warmup, fee_bps=fee), ensure_ascii=False, indent=2))
