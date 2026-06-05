"""常驻刷新服务:定时拉最新K线 + 重算官方报告,让监控/灯号提醒真正"活"起来。

没有它,reports/ 是冻结快照,机器人的"灯号翻转提醒"永远不会响。
有了它,新K线一收盘 → 重算 → 机器人盯盘 loop 读到新灯号 → 推送给你。

注意:雷达按**收盘K线**算灯号(防偷看),所以灯号在 bar 收盘时更新——
1D 约一天一次、4H 每 4 小时、8H 每 8 小时。刷新间隔设小只是让"新收盘"更快被发现,
不会让灯号逐 tick 跳(那是错的)。现价等实时行情是另一层,这里只管雷达层。

配置(环境变量)
    LIVE_REFRESH_SYMBOLS   逗号分隔,默认 BTC-USDT,ETH-USDT(越多越吃 OKX 限频)
    LIVE_REFRESH_BARS      默认 1D,4H,8H
    LIVE_REFRESH_INTERVAL_SEC  刷新间隔秒,默认 300(5 分钟)
    LIVE_REFRESH_DAYS      历史窗口,默认 3650(报告需长 warmup)

运行(需联网 OKX)
    uv run python -m backend_py.live_refresh           # 常驻循环
    uv run python -m backend_py.live_refresh --once    # 跑一轮就退(便于测试/cron)

机密无关;只写 data/ 与 reports/(已分别 gitignore / 作为产物)。
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

from .reports_reader import REPORTS_DIR, report_stem

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("live_refresh")

SYMBOLS = [s.strip() for s in os.environ.get("LIVE_REFRESH_SYMBOLS", "BTC-USDT,ETH-USDT").split(",") if s.strip()]
BARS = [b.strip() for b in os.environ.get("LIVE_REFRESH_BARS", "1D,4H,8H").split(",") if b.strip()]
INTERVAL_SEC = int(os.environ.get("LIVE_REFRESH_INTERVAL_SEC", "300"))
DAYS = os.environ.get("LIVE_REFRESH_DAYS", "3650")


def _run(module: str, extra: list[str]) -> None:
    cmd = [sys.executable, "-m", module, "--symbols", *SYMBOLS, "--bars", ",".join(BARS), "--days", DAYS, *extra]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        tail = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-12:])
        raise RuntimeError(f"{module} exit={result.returncode}\n{tail}")


def report_last_dates() -> dict[str, str | None]:
    """读当前各 (品种,周期) 报告的最后K线日期,用于日志展示刷新效果。"""
    out: dict[str, str | None] = {}
    for bar in BARS:
        for sym in SYMBOLS:
            try:
                stem = report_stem(sym, bar)
                path = REPORTS_DIR / f"{stem}_market_weather_router.json"
                meta = json.loads(path.read_text(encoding="utf-8")).get("metadata", {})
                out[f"{sym} {bar}"] = meta.get("lastDate")
            except Exception:  # noqa: BLE001
                out[f"{sym} {bar}"] = None
    return out


def refresh_once() -> dict[str, str | None]:
    """一轮:下载最新 → 清洗 → 重算官方报告(含机器人读的多周期 summary)。"""
    log.info("refresh start · symbols=%s bars=%s", SYMBOLS, BARS)
    _run("backend_py.run_data_pipeline", [])                       # download + clean
    _run("backend_py.run_full_pipeline", ["--skip-download", "--official"])  # 重算 official 报告
    last = report_last_dates()
    log.info("refresh done · lastDates=%s", last)
    return last


def main(argv: list[str] | None = None) -> None:
    args = list(argv if argv is not None else sys.argv[1:])
    once = "--once" in args
    log.info(
        "live_refresh starting · interval=%ss · once=%s · symbols=%s · bars=%s",
        INTERVAL_SEC, once, SYMBOLS, BARS,
    )
    while True:
        started = datetime.now(timezone.utc)
        try:
            refresh_once()
        except Exception as error:  # noqa: BLE001 - keep the refresher alive across transient OKX/network errors
            log.warning("refresh cycle failed: %s", error)
        if once:
            return
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        time.sleep(max(5, INTERVAL_SEC - elapsed))


if __name__ == "__main__":
    main()
