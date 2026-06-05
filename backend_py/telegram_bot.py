"""市场天气雷达 · Telegram 适配器(大脑见 radar_brain)。

能力:自然语言问答(Claude/DeepSeek)、主动盯盘推送、每日播报、按需命令。
红线:只描述环境/状态,绝不预测涨跌、不给买卖信号(见 docs/gate1-conclusion.md)。

运行(需联网 api.telegram.org + 所选模型 API)
    uv pip install -e ".[bot]"
    export TELEGRAM_BOT_TOKEN=...        # @BotFather 申请
    export ANTHROPIC_API_KEY=...         # 或 BOT_LLM_PROVIDER=deepseek + DEEPSEEK_API_KEY
    uv run python -m backend_py.telegram_bot

机密只走环境变量,绝不提交。状态存 data/telegram_state.json(data/ 已 gitignore)。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .radar_brain import (
    DEFAULT_BAR,
    PROVIDER,
    ask_llm,
    fmt_weather,
    provider_key_env,
    reader,
    resolve_bar,
    resolve_instrument,
    tool_get_market_weather,
    tool_market_overview,
)
from .reports_reader import PROJECT_ROOT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("telegram_bot")

STATE_PATH = PROJECT_ROOT / "data" / "telegram_state.json"
POLL_INTERVAL_SEC = int(os.environ.get("BOT_ALERT_INTERVAL_SEC", "900"))  # 盯盘轮询(默认 15 分钟)
BROADCAST_HOUR_UTC = int(os.environ.get("BOT_BROADCAST_HOUR_UTC", "1"))   # 每日播报 UTC 小时
HISTORY_TURNS = 12

_state_lock = threading.Lock()


# ---- 状态持久化 ----------------------------------------------------------- #
def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - corrupt state shouldn't crash the bot
            log.warning("state file unreadable; starting fresh")
    return {"chats": {}, "lastGates": {}}


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _chat(state: dict[str, Any], chat_id: str) -> dict[str, Any]:
    return state["chats"].setdefault(chat_id, {"watch": [], "daily": False})


# ---- Telegram HTTP(标准库,零额外依赖) -------------------------------- #
def tg_call(method: str, params: dict[str, Any], timeout: int = 35) -> dict[str, Any]:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def send(chat_id: str | int, text: str) -> None:
    try:
        tg_call("sendMessage", {"chat_id": chat_id, "text": text[:4096]}, timeout=20)
    except Exception as error:  # noqa: BLE001 - a failed send shouldn't kill the loop
        log.warning("sendMessage failed for %s: %s", chat_id, error)


# ---- 命令 ---------------------------------------------------------------- #
HELP = (
    "📡 市场天气雷达机器人\n"
    "我只描述当下市场环境/状态,不预测涨跌、不给买卖信号。\n\n"
    "直接发问(自然语言):如「BTC 现在什么天气」「哪些币是绿灯」「4H 全市场概览」。\n\n"
    "命令:\n"
    "/weather <品种> [周期] — 查天气,如 /weather BTC 1D\n"
    "/overview [周期] — 全市场灯号概览\n"
    "/watch <品种> [周期] — 盯盘,灯号翻转时提醒\n"
    "/unwatch <品种> [周期] — 取消盯盘\n"
    "/watchlist — 我的盯盘列表\n"
    "/daily on|off — 每日天气播报开关\n"
    "/reset — 清空对话上下文\n"
    "/help — 帮助\n\n"
    "⚠️ 雷达经回测无已证实可交易 edge:它是环境/风控描述器,不是赚钱信号。盈亏自负。"
)


def parse_symbol_bar(args: list[str]) -> tuple[str | None, str]:
    inst = resolve_instrument(args[0]) if args else None
    bar = resolve_bar(args[1]) if len(args) > 1 else DEFAULT_BAR
    return inst, bar


def handle_command(chat_id: str, text: str, histories: dict[str, list]) -> None:
    parts = text.strip().split()
    cmd = parts[0].lower().lstrip("/").split("@")[0]
    args = parts[1:]
    state = load_state()

    if cmd in ("start", "help"):
        send(chat_id, HELP)
    elif cmd == "weather":
        inst, bar = parse_symbol_bar(args)
        if not inst:
            send(chat_id, "用法:/weather BTC 1D")
            return
        send(chat_id, fmt_weather(tool_get_market_weather(inst, bar)))
    elif cmd == "overview":
        bar = resolve_bar(args[0] if args else None)
        ov = tool_market_overview(bar)
        if ov.get("status") == "no_data":
            send(chat_id, f"{bar}:暂无概览数据")
        else:
            gc = ov.get("gateCounts") or {}
            lines = "\n".join(f"  {g}: {n}" for g, n in gc.items())
            send(chat_id, f"🗺️ {bar} 全市场灯号分布({ov.get('rowCount')} 品种):\n{lines}\n(只描述环境分布,不含买卖信号)")
    elif cmd == "watch":
        inst, bar = parse_symbol_bar(args)
        if not inst:
            send(chat_id, "用法:/watch BTC 1D")
            return
        with _state_lock:
            state = load_state()
            ch = _chat(state, chat_id)
            entry = {"instrument": inst, "bar": bar}
            if entry not in ch["watch"]:
                ch["watch"].append(entry)
            save_state(state)
        send(chat_id, f"👁️ 已盯盘 {inst} {bar}。灯号翻转时我会提醒你。")
    elif cmd == "unwatch":
        inst, bar = parse_symbol_bar(args)
        with _state_lock:
            state = load_state()
            ch = _chat(state, chat_id)
            ch["watch"] = [e for e in ch["watch"] if not (e["instrument"] == inst and e["bar"] == bar)]
            save_state(state)
        send(chat_id, f"已取消盯盘 {inst} {bar}。")
    elif cmd == "watchlist":
        ch = _chat(state, chat_id)
        if not ch["watch"]:
            send(chat_id, "盯盘列表为空。用 /watch BTC 1D 添加。")
        else:
            send(chat_id, "👁️ 盯盘列表:\n" + "\n".join(f"  {e['instrument']} {e['bar']}" for e in ch["watch"]))
    elif cmd == "daily":
        on = bool(args) and args[0].lower() in ("on", "开", "1", "true")
        with _state_lock:
            state = load_state()
            _chat(state, chat_id)["daily"] = on
            save_state(state)
        send(chat_id, f"每日播报已{'开启' if on else '关闭'}。")
    elif cmd == "reset":
        histories.pop(chat_id, None)
        send(chat_id, "对话上下文已清空。")
    else:
        send(chat_id, "未知命令。/help 看用法。")


def handle_message(chat_id: str, text: str, histories: dict[str, list]) -> None:
    if text.startswith("/"):
        handle_command(chat_id, text, histories)
        return
    history = histories.setdefault(chat_id, [])
    history.append({"role": "user", "content": text})
    try:
        reply = ask_llm(history)
    except Exception as error:  # noqa: BLE001 - surface LLM/config errors to the user
        log.exception("ask_llm failed")
        msg = str(error)
        if "API_KEY" in msg.upper() or "api_key" in msg.lower():
            reply = f"智能问答需要配置模型 API key(当前 provider={PROVIDER})。命令(/weather /overview 等)仍可用。"
        else:
            reply = f"出错了:{msg[:200]}"
        history.pop()
        send(chat_id, reply)
        return
    history.append({"role": "assistant", "content": reply})
    del history[: max(0, len(history) - HISTORY_TURNS * 2)]
    send(chat_id, reply)


# ---- 后台:盯盘告警 + 每日播报 ----------------------------------------- #
def alert_loop() -> None:
    while True:
        try:
            with _state_lock:
                state = load_state()
                watched: dict[tuple[str, str], list[str]] = {}
                for chat_id, ch in state["chats"].items():
                    for e in ch.get("watch", []):
                        watched.setdefault((e["instrument"], e["bar"]), []).append(chat_id)
                last_gates = state.setdefault("lastGates", {})
                changed = False
                for (inst, bar), chat_ids in watched.items():
                    row = reader.current(instrument=inst, bar=bar)
                    gate = row.get("gate") if row else None
                    if not gate:
                        continue
                    key = f"{inst}|{bar}"
                    prev = last_gates.get(key)
                    if prev is not None and prev != gate:
                        for cid in chat_ids:
                            send(cid, f"🔔 灯号翻转 {inst} {bar}:{prev} → {gate}\n(环境描述变化,非买卖信号)")
                    if prev != gate:
                        last_gates[key] = gate
                        changed = True
                if changed:
                    save_state(state)
        except Exception as error:  # noqa: BLE001 - keep the watcher alive
            log.warning("alert_loop error: %s", error)
        time.sleep(POLL_INTERVAL_SEC)


def broadcast_loop() -> None:
    last_sent_date = None
    while True:
        try:
            now = datetime.now(timezone.utc)
            today = now.date().isoformat()
            if now.hour == BROADCAST_HOUR_UTC and last_sent_date != today:
                state = load_state()
                for chat_id, ch in state["chats"].items():
                    if not ch.get("daily"):
                        continue
                    lines = []
                    for e in ch.get("watch", []) or [{"instrument": "BTC-USDT", "bar": DEFAULT_BAR}]:
                        p = tool_get_market_weather(e["instrument"], e["bar"])
                        if p.get("status") == "ok":
                            lines.append(f"  {p['instrument']} {p['bar']}: {p['gate']} / {p.get('topWeatherRoute')}")
                    if lines:
                        send(chat_id, "🌅 每日天气播报\n" + "\n".join(lines) + "\n(只描述环境,不含买卖信号)")
                last_sent_date = today
        except Exception as error:  # noqa: BLE001 - keep the broadcaster alive
            log.warning("broadcast_loop error: %s", error)
        time.sleep(300)


# ---- 主循环:长轮询 getUpdates ----------------------------------------- #
def main() -> None:
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        raise SystemExit("缺少 TELEGRAM_BOT_TOKEN(@BotFather 申请),见模块文档。")
    if not os.environ.get(provider_key_env()):
        log.warning("未设 %s(provider=%s):命令可用,但自然语言问答会提示配置。", provider_key_env(), PROVIDER)
    log.info("telegram bot started; LLM provider=%s", PROVIDER)

    histories: dict[str, list] = {}
    threading.Thread(target=alert_loop, daemon=True).start()
    threading.Thread(target=broadcast_loop, daemon=True).start()

    offset = 0
    while True:
        try:
            resp = tg_call("getUpdates", {"offset": offset, "timeout": 30}, timeout=35)
        except (urllib.error.URLError, TimeoutError) as error:
            log.warning("getUpdates network error: %s; retrying", error)
            time.sleep(3)
            continue
        except Exception as error:  # noqa: BLE001
            log.warning("getUpdates error: %s", error)
            time.sleep(3)
            continue
        for update in resp.get("result", []):
            offset = update["update_id"] + 1
            msg = update.get("message") or update.get("channel_post")
            if not msg or "text" not in msg:
                continue
            chat_id = str(msg["chat"]["id"])
            try:
                handle_message(chat_id, msg["text"], histories)
            except Exception as error:  # noqa: BLE001 - one bad message shouldn't kill the bot
                log.exception("handle_message failed")
                send(chat_id, f"处理出错:{str(error)[:200]}")


if __name__ == "__main__":
    main()
