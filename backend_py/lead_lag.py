"""lead-lag 统计:检验"XRP 先行"是真领先还是只是高相关/高β(可证伪)。

诚实方法论(对抗确认偏差):
1. 滞后互相关:corr(X_t, Y_{t+k}),k>0 表示 X 领先 Y。对每对币找峰值滞后 k*。
2. 公平对照:把**每个币**都当候选领先者算"领先分",排名。XRP 不在前列 → "先行"证伪。
3. 方向跟随:X 大动(|收益|前 20%)时,下一根 Y 同向的比例 vs 基准率(看 lift)。
4. 跨段稳定:整段 + 前后半段分别看,别只在某一段成立。

数据:币安公开 K 线(无需 key,只用标准库)。在能连 api.binance.com 的机器上跑。
红线:这是**描述性统计**——就算测出 XRP 真领先几根bar,扣成本能不能赚钱是另一回事
(Gate-1 已反复证明"看着有规律"多半不可交易)。本脚本不给买卖建议。

用法:
    python -m backend_py.lead_lag
    python -m backend_py.lead_lag --symbols XRP,BTC,ETH,SOL,BNB,DOGE,ADA,LINK --interval 1d --limit 1000 --maxlag 5
    python -m backend_py.lead_lag --interval 1h --limit 1000     # 小时级看更细的领先
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.parse
import urllib.request

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
DEFAULT_SYMBOLS = ["XRP", "BTC", "ETH", "SOL", "BNB", "DOGE", "ADA", "LINK"]


def fetch_closes(symbol: str, interval: str, limit: int) -> dict[int, float]:
    """拉某币 USDT 现货 K 线,返回 {openTime(ms): close}。"""
    q = urllib.parse.urlencode({"symbol": f"{symbol}USDT", "interval": interval, "limit": limit})
    req = urllib.request.Request(f"{BINANCE_KLINES}?{q}", headers={"User-Agent": "whd-leadlag/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return {int(row[0]): float(row[4]) for row in data}


def log_returns(closes: list[float]) -> list[float]:
    out = []
    for i in range(1, len(closes)):
        prev, cur = closes[i - 1], closes[i]
        out.append(math.log(cur / prev) if prev > 0 and cur > 0 else 0.0)
    return out


def pearson(a: list[float], b: list[float]) -> float:
    n = len(a)
    if n < 3:
        return 0.0
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return 0.0
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return cov / math.sqrt(va * vb)


def lagged_corr(x: list[float], y: list[float], k: int) -> float:
    """corr(x_t, y_{t+k});k>0 即 x 领先 y k 根。"""
    if k >= 0:
        xs, ys = x[: len(x) - k], y[k:]
    else:
        xs, ys = x[-k:], y[: len(y) + k]
    m = min(len(xs), len(ys))
    return pearson(xs[:m], ys[:m])


def best_lag(x: list[float], y: list[float], maxlag: int) -> tuple[int, float]:
    """返回 (峰值滞后 k*, 该处相关)。|相关|最大处。"""
    best_k, best_c = 0, -2.0
    for k in range(-maxlag, maxlag + 1):
        c = lagged_corr(x, y, k)
        if abs(c) > abs(best_c) or best_c == -2.0:
            best_k, best_c = k, c
    return best_k, best_c


def follow_through(x: list[float], y: list[float], pct: float = 0.8) -> dict[str, float]:
    """x 大动(|收益| 分位 >= pct)时,下一根 y 同向比例 vs 基准。"""
    if len(x) < 30:
        return {"n": 0, "hit": 0.0, "base": 0.0, "lift": 0.0}
    mags = sorted(abs(v) for v in x[:-1])
    thr = mags[int(len(mags) * pct)]
    base = sum(1 for i in range(len(y)) if (x[i] > 0) == (y[i] > 0)) / max(1, len(y))  # 同向基准率
    hits, n = 0, 0
    for t in range(len(x) - 1):
        if abs(x[t]) >= thr and x[t] != 0:
            n += 1
            if (x[t] > 0) == (y[t + 1] > 0):
                hits += 1
    hit = hits / n if n else 0.0
    return {"n": n, "hit": hit, "base": base, "lift": hit - base}


def align(closes_by_symbol: dict[str, dict[int, float]]) -> tuple[list[int], dict[str, list[float]]]:
    """按公共 openTime 对齐所有币的收盘。"""
    common = set.intersection(*(set(c.keys()) for c in closes_by_symbol.values()))
    times = sorted(common)
    series = {s: [closes_by_symbol[s][t] for t in times] for s in closes_by_symbol}
    return times, series


def analyze(returns: dict[str, list[float]], symbols: list[str], maxlag: int) -> dict:
    """对每对币算峰值滞后;给每个币一个'领先分'(平均领先的根数,正=倾向领先)。"""
    lead_score: dict[str, float] = {s: 0.0 for s in symbols}
    pairs = []
    for i, a in enumerate(symbols):
        for b in symbols:
            if a == b:
                continue
            k, c = best_lag(returns[a], returns[b], maxlag)
            pairs.append({"leader": a, "follower": b, "bestLag": k, "corr": round(c, 3)})
            # a 领先 b 则 k>0;累计到 a 的领先分(用相关加权,只算正相关的领先)
            if c > 0:
                lead_score[a] += k * c
    ranking = sorted(((s, round(v, 3)) for s, v in lead_score.items()), key=lambda kv: kv[1], reverse=True)
    return {"pairs": pairs, "leadRanking": ranking}


def run(symbols: list[str], interval: str, limit: int, maxlag: int) -> None:
    print(f"# lead-lag · symbols={symbols} interval={interval} limit={limit} maxlag={maxlag}\n")
    closes_by_symbol: dict[str, dict[int, float]] = {}
    for s in symbols:
        try:
            closes_by_symbol[s] = fetch_closes(s, interval, limit)
            time.sleep(0.2)
        except Exception as error:  # noqa: BLE001
            print(f"!! fetch {s} 失败: {error}")
    if "XRP" not in closes_by_symbol or len(closes_by_symbol) < 2:
        print("数据不足,退出。")
        return

    times, series = align(closes_by_symbol)
    print(f"对齐后样本根数: {len(times)}\n")
    returns = {s: log_returns(v) for s, v in series.items()}
    syms = [s for s in symbols if s in returns]

    def report(rets: dict[str, list[float]], label: str) -> None:
        res = analyze(rets, syms, maxlag)
        print(f"## {label} — 领先分排名(越高越倾向领先;k>0=领先)")
        for s, v in res["leadRanking"]:
            print(f"   {s:<5} {v:+.3f}")
        # XRP 对各币的峰值滞后
        print(f"\n   XRP→各币 峰值滞后(k>0=XRP领先,k=0=同步,k<0=XRP滞后):")
        for p in res["pairs"]:
            if p["leader"] == "XRP":
                tag = "XRP领先" if p["bestLag"] > 0 else ("同步" if p["bestLag"] == 0 else "XRP滞后")
                print(f"     XRP vs {p['follower']:<5} k*={p['bestLag']:+d} corr={p['corr']:+.3f}  [{tag}]")
        # 方向跟随:XRP 大动 → 各币下一根
        print(f"\n   XRP 大动后,各币下一根同向命中率 vs 基准(lift>0 才算 XRP 有预示):")
        for b in syms:
            if b == "XRP":
                continue
            ft = follow_through(rets["XRP"], rets[b])
            print(f"     XRP→{b:<5} n={ft['n']:>4} 命中={ft['hit']:.3f} 基准={ft['base']:.3f} lift={ft['lift']:+.3f}")
        print()

    report(returns, "全段")
    half = len(times) // 2
    if half > 40:
        report({s: log_returns([closes_by_symbol[s][t] for t in times[:half]]) for s in syms}, "前半段")
        report({s: log_returns([closes_by_symbol[s][t] for t in times[half:]]) for s in syms}, "后半段")

    print("=" * 60)
    print("诚实读法:")
    print(" - 领先分排名里 XRP 若不靠前 / 各对 k* 多为 0 → 'XRP先行'是错觉(其实是高相关/高β同步)。")
    print(" - k* 一致 >0 且 lift 明显 >0、且前后半段都成立 → 才算真有领先性。")
    print(" - 即便真领先:这是 in-sample 描述,扣手续费+滑点能否变钱另说(Gate-1:多半不能)。")
    print(" - 本脚本只描述,不给买卖建议。")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="XRP 先行?lead-lag 可证伪统计")
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    p.add_argument("--interval", default="1d")
    p.add_argument("--limit", type=int, default=1000)
    p.add_argument("--maxlag", type=int, default=5)
    args = p.parse_args(argv if argv is not None else sys.argv[1:])
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if "XRP" not in symbols:
        symbols = ["XRP", *symbols]
    run(symbols, args.interval, args.limit, args.maxlag)


if __name__ == "__main__":
    main()
