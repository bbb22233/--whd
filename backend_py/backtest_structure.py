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
        "byReason": {k: sum(1 for t in trades if t.get("reason") == k) for k in ("tp", "stop", "timeout")},
    }


def backtest_chips(candles: list[dict[str, Any]], warmup: int = 250, fee_bps: float = 5.0,
                   slip_bps: float = 5.0, max_hold: int = 80, buffer_pct: float = 0.05,
                   risk_budget: float = 0.02, max_leverage: float = 3.0,
                   tp_fracs: tuple[float, ...] = (1 / 3, 1 / 3, 1 / 3)) -> dict[str, Any]:
    """v3 完整筹码:多次清算(逆推三档各止盈)+ 留底仓 + 保护(TP1→保本、TP2→TP1)。
    冲着"让赢的跑、亏的截断"——把 v2 的'到TP1全平、赢得太小'改成'分批止盈+底仓吃大顺势'。"""
    cost = (fee_bps + slip_bps) / 10000.0
    trades: list[dict[str, Any]] = []
    pos: dict[str, Any] | None = None
    prev_state = ""

    for t in range(warmup, len(candles)):
        bar = candles[t]
        if pos:
            d = 1 if pos["side"] == "long" else -1
            # 1) 止损打在剩余仓上
            stopped = (pos["side"] == "long" and bar["low"] <= pos["stop"]) or \
                      (pos["side"] == "short" and bar["high"] >= pos["stop"])
            if stopped and pos["remaining"] > 1e-9:
                pos["realized"] += pos["remaining"] * ((pos["stop"] / pos["entry"] - 1) * d)
                pos["remaining"] = 0.0
            # 2) 逆推三档分批止盈(按顺序)
            for k, tp in enumerate(pos["tps"]):
                if k in pos["filledTps"] or pos["remaining"] <= 1e-9:
                    continue
                reach = (pos["side"] == "long" and bar["high"] >= tp) or \
                        (pos["side"] == "short" and bar["low"] <= tp)
                if reach:
                    portion = min(pos["tpFracs"][k], pos["remaining"])
                    pos["realized"] += portion * ((tp / pos["entry"] - 1) * d)
                    pos["remaining"] -= portion
                    pos["filledTps"].add(k)
                    if k == 0:
                        pos["stop"] = pos["entry"]       # TP1 后保本
                    elif k == 1:
                        pos["stop"] = pos["tps"][0]       # TP2 后移到 TP1(锁底仓利润)
            # 3) 超时平剩余
            if pos["remaining"] > 1e-9 and t - pos["entryIdx"] >= max_hold:
                pos["realized"] += pos["remaining"] * ((bar["close"] / pos["entry"] - 1) * d)
                pos["remaining"] = 0.0
            if pos["remaining"] <= 1e-9:
                trades.append({"side": pos["side"], "entry": pos["entry"], "stop": pos["initStop"],
                               "ret": pos["realized"] - 2 * cost})
                pos = None

        if pos is None:
            s = analyze_structure(candles[: t + 1])
            st = (s.get("breakout") or {}).get("state", "") if s else ""
            if st in ("confirmed_up", "confirmed_down") and st != prev_state:
                side = "long" if st == "confirmed_up" else "short"
                piv = s["latestPivot"]
                buf = buffer_pct * (piv["high"] - piv["low"])
                lad = reverse_fib_ladder(piv["high"], piv["low"])
                tps = [x["price"] for x in (lad["up"] if side == "long" else lad["down"])]
                stop = (piv["low"] - buf) if side == "long" else (piv["high"] + buf)
                entry = bar["close"]
                ok = (side == "long" and tps[0] > entry > stop) or (side == "short" and tps[0] < entry < stop)
                if ok:
                    pos = {"side": side, "entry": entry, "stop": stop, "initStop": stop, "tps": tps,
                           "tpFracs": list(tp_fracs), "filledTps": set(), "remaining": 1.0,
                           "realized": 0.0, "entryIdx": t}
            prev_state = st if st else prev_state

    return _stats(trades, risk_budget, max_leverage)


def backtest_grid(candles: list[dict[str, Any]], warmup: int = 250, fee_bps: float = 5.0,
                  slip_bps: float = 5.0, n_levels: int = 8, buffer_pct: float = 0.05,
                  grid_stake: float = 0.5, lookback: int = 400, restep: int = 6,
                  use_zone: bool = False) -> dict[str, Any]:
    """v4 循环网格(震荡模式,框架主菜):
    inside 时在箱子里铺 n_levels 格 → 价格落到一格买、涨一格卖、清掉回来再接(循环收割震荡);
    跌破箱底(边际线)全平止损;突破箱顶则收尾。grid_stake = 整个网格占用资金比例。
    为 4H/大数据加速:结构用最近 lookback 根的滚动窗口、每 restep 根才重算一次。
    use_zone=True 用中枢核心区(更紧的区间布局)而非整段摆动。
    """
    cost = (fee_bps + slip_bps) / 10000.0
    eq, peak, maxdd = 1.0, 1.0, 0.0
    cycles, blowups = 0, 0
    grid: dict[str, Any] | None = None
    last_check = -10 ** 9

    def apply(r: float) -> None:
        nonlocal eq, peak, maxdd
        eq *= (1 + r)
        peak = max(peak, eq)
        maxdd = max(maxdd, (peak - eq) / peak)

    for t in range(warmup, len(candles)):
        bar = candles[t]
        if grid is None and t - last_check >= restep:
            last_check = t
            win = candles[max(0, t - lookback): t + 1]
            s = analyze_structure(win)
            st = (s.get("breakout") or {}).get("state", "") if s else ""
            piv = s.get("latestPivot") if s else None
            if st == "inside" and piv:
                lo = piv["zoneLow"] if use_zone else piv["low"]
                hi = piv["zoneHigh"] if use_zone else piv["high"]
                if hi > lo:
                    levels = [lo + i * (hi - lo) / n_levels for i in range(n_levels + 1)]
                    grid = {"levels": levels, "spacing": (hi - lo) / n_levels,
                            "holding": [False] * (n_levels + 1), "buy": [0.0] * (n_levels + 1),
                            "marginLo": lo - buffer_pct * (hi - lo), "marginHi": hi + buffer_pct * (hi - lo)}
        if grid:
            unit = grid_stake / n_levels
            if bar["low"] <= grid["marginLo"]:                 # 跌破边际线 → 全平止损
                for i, h in enumerate(grid["holding"]):
                    if h:
                        apply(unit * ((grid["marginLo"] / grid["buy"][i] - 1) - 2 * cost))
                blowups += 1
                grid = None
                continue
            if bar["high"] >= grid["marginHi"]:                # 突破箱顶 → 收尾(剩余按箱顶平)
                for i, h in enumerate(grid["holding"]):
                    if h:
                        apply(unit * ((grid["marginHi"] / grid["buy"][i] - 1) - 2 * cost))
                grid = None
                continue
            # 网格成交:先卖(已持仓涨一格止盈),再买(空格落到位)
            for i, b in enumerate(grid["levels"]):
                if grid["holding"][i] and bar["high"] >= grid["buy"][i] + grid["spacing"]:
                    apply(unit * (grid["spacing"] / grid["buy"][i] - 2 * cost))
                    grid["holding"][i] = False
                    cycles += 1
            for i, b in enumerate(grid["levels"]):
                if not grid["holding"][i] and bar["low"] <= b:
                    grid["holding"][i] = True
                    grid["buy"][i] = b

    return {"cycles": cycles, "blowups": blowups,
            "totalReturnPct": round(100 * (eq - 1), 1), "maxDrawdownPct": round(100 * maxdd, 1)}


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/data/clean/BTC_USDT_1D_clean.json"
    warmup = int(sys.argv[2]) if len(sys.argv) > 2 else 250
    fee = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
    candles = json.loads(Path(path).read_text(encoding="utf-8"))["candles"]
    print(f"# 回测 {Path(path).name}  bars={len(candles)}  warmup={warmup}  fee={fee}bps/边")
    print(json.dumps(backtest(candles, warmup=warmup, fee_bps=fee), ensure_ascii=False, indent=2))
