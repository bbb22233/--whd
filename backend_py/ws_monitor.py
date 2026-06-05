"""实时监控:OKX WebSocket 增量接入 —— 历史只回填一次,之后只接"新收盘bar"。

对比 live_refresh(每轮重下全量历史,蠢):本模块用 WS 订阅蜡烛频道,
**只在收到 confirm="1"(已收盘)的新bar时**才追加+增量重算,几乎不耗网络。

数据流(无历史重下):
    OKX WS candle 频道 ──收盘bar──▶ 追加到 data/raw ──▶ 重清洗(--clean-only,不下载)
        ──▶ 重算官方报告(--skip-download --official)──▶ 机器人/前端读到新灯号

对齐:OKX 原生只有 1D/4H/1W;**8H 由 4H 聚合**——故订阅原生 1D/4H/1W,
4H 收盘时官方产线顺带重算 8H。WS 频道名 = "candle"+REST的bar串,保证周期边界一致。

前置:先回填一次历史(`run_data_pipeline` / `run_full_pipeline`),让 data/raw 存在。
本模块不重下历史,只接增量。

配置(环境变量)
    WS_MONITOR_SYMBOLS   逗号分隔,默认 BTC-USDT,ETH-USDT
    WS_MONITOR_BARS      默认 1D,4H,8H(8H 自动由 4H 派生)

运行(需联网 OKX WS)
    uv pip install -e ".[live]"
    uv run python -m backend_py.ws_monitor
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from typing import Any

from .reports_reader import DATA_RAW_DIR, report_stem
from .research.config import file_stem, parse_args

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ws_monitor")

OKX_WS_URL = "wss://ws.okx.com:8443/ws/v5/business"  # 蜡烛频道在 business 端点
SYMBOLS = [s.strip() for s in os.environ.get("WS_MONITOR_SYMBOLS", "BTC-USDT,ETH-USDT").split(",") if s.strip()]
BARS = [b.strip() for b in os.environ.get("WS_MONITOR_BARS", "1D,4H,8H").split(",") if b.strip()]

# OKX 原生蜡烛周期(8H 非原生,由 4H 聚合)。订阅原生,8H 跟着 4H 重算。
NATIVE_BARS = [b for b in BARS if b != "8H"]
if "8H" in BARS and "4H" not in NATIVE_BARS:
    NATIVE_BARS.append("4H")
DERIVE_8H = "8H" in BARS

# 已处理的收盘bar(去重:OKX 可能多次推同一根)
_seen: dict[tuple[str, str], int] = {}
_rebuild_lock = asyncio.Lock()


def stem_for(symbol: str, bar: str) -> str:
    return file_stem(parse_args(["--instrument", symbol, "--bar", bar]))


def append_raw_row(symbol: str, bar: str, row: list[Any]) -> bool:
    """把一根 OKX 蜡烛数组按时间戳去重追加进 data/raw。返回是否真的新增。"""
    path = DATA_RAW_DIR / f"{stem_for(symbol, bar)}_raw.json"
    if not path.exists():
        log.warning("raw missing for %s %s (%s) —— 先回填历史再开实时", symbol, bar, path.name)
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows") or []
    ts = str(int(float(row[0])))
    existing = {str(int(float(r[0]))): i for i, r in enumerate(rows)}
    if ts in existing:
        rows[existing[ts]] = row  # 覆盖(收盘值可能比之前的未收盘更准)
    else:
        rows.append(row)
    rows.sort(key=lambda r: float(r[0]))
    payload["rows"] = rows
    payload["rowCount"] = len(rows)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return ts not in existing


def _run(module: str, extra: list[str]) -> None:
    cmd = [sys.executable, "-m", module, *extra]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        tail = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-10:])
        raise RuntimeError(f"{module} exit={result.returncode}\n{tail}")


def rebuild(symbol: str, native_bar: str) -> str | None:
    """重清洗 + 重算官方报告(不下载)。4H 时连带重算 8H。返回新 lastDate。"""
    rebuild_bars = [native_bar] + (["8H"] if native_bar == "4H" and DERIVE_8H else [])
    _run("backend_py.run_data_pipeline", ["--clean-only", "--symbols", symbol, "--bars", native_bar])
    _run("backend_py.run_full_pipeline", ["--skip-download", "--official", "--symbols", symbol, "--bars", ",".join(rebuild_bars)])
    try:
        path = __import__("backend_py.reports_reader", fromlist=["REPORTS_DIR"]).REPORTS_DIR / f"{report_stem(symbol, native_bar)}_market_weather_router.json"
        return json.loads(path.read_text(encoding="utf-8")).get("metadata", {}).get("lastDate")
    except Exception:  # noqa: BLE001
        return None


async def handle_closed_bar(symbol: str, bar: str, row: list[Any]) -> None:
    ts = int(float(row[0]))
    key = (symbol, bar)
    if _seen.get(key) == ts:
        return
    _seen[key] = ts
    async with _rebuild_lock:  # 串行重算,避免并发写 data/reports
        added = await asyncio.to_thread(append_raw_row, symbol, bar, row)
        if not added:
            return
        try:
            last = await asyncio.to_thread(rebuild, symbol, bar)
            log.info("✓ %s %s 收盘bar已并入,报告 lastDate=%s", symbol, bar, last)
        except Exception as error:  # noqa: BLE001 - keep monitor alive on rebuild error
            log.warning("rebuild %s %s failed: %s", symbol, bar, error)


def subscribe_args() -> list[dict[str, str]]:
    return [{"channel": f"candle{bar}", "instId": sym} for bar in NATIVE_BARS for sym in SYMBOLS]


async def run() -> None:
    import websockets  # 延迟导入(.[live])

    args = subscribe_args()
    log.info("ws_monitor connecting · symbols=%s native_bars=%s derive8H=%s", SYMBOLS, NATIVE_BARS, DERIVE_8H)
    while True:
        try:
            async with websockets.connect(OKX_WS_URL, ping_interval=None, max_queue=None) as ws:
                await ws.send(json.dumps({"op": "subscribe", "args": args}))
                log.info("subscribed %d channels", len(args))
                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=25)
                    except asyncio.TimeoutError:
                        await ws.send("ping")  # OKX 保活:25s 无数据主动 ping
                        continue
                    if raw == "pong":
                        continue
                    msg = json.loads(raw)
                    if msg.get("event"):  # subscribe/error 回执
                        if msg.get("event") == "error":
                            log.warning("ws event error: %s", msg)
                        continue
                    arg = msg.get("arg") or {}
                    channel = arg.get("channel", "")
                    inst = arg.get("instId", "")
                    if not channel.startswith("candle") or not msg.get("data"):
                        continue
                    bar = channel[len("candle"):]
                    for item in msg["data"]:
                        if len(item) >= 9 and str(item[8]) == "1":  # confirm=1 已收盘
                            await handle_closed_bar(inst, bar, list(item))
        except Exception as error:  # noqa: BLE001 - reconnect on any drop
            log.warning("ws connection error: %s; reconnect in 5s", error)
            await asyncio.sleep(5)


def main() -> None:
    if not SYMBOLS or not NATIVE_BARS:
        raise SystemExit("WS_MONITOR_SYMBOLS / WS_MONITOR_BARS 配置为空")
    asyncio.run(run())


if __name__ == "__main__":
    main()
