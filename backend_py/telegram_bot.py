"""Claude-powered Telegram bot for the market weather radar.

Capabilities
------------
- 自然语言问答:用 Claude(opus-4-8)+工具实时查雷达状态回答大白话提问。
- 主动盯盘推送:后台轮询,被盯品种 regime/灯号翻转就推送。
- 定时播报:每日固定时间推送关注品种的天气概览。
- 按需命令:/weather /watch /overview 等,零 LLM、秒回。

定位红线(贯穿系统提示)
------------------------
雷达只描述"当下是什么环境/状态",**绝不给买卖信号、绝不预测涨跌**(见 docs/gate1-conclusion.md)。
机器人的"智能"是会聊、会解释、会盯盘——不是会喊单。

智能内核可插拔(BOT_LLM_PROVIDER)
----------------------------------
    claude(默认): export ANTHROPIC_API_KEY=...   # 最智能
    deepseek:     export BOT_LLM_PROVIDER=deepseek; export DEEPSEEK_API_KEY=...   # 更便宜,OpenAI 兼容
    openai 兼容:  export BOT_LLM_PROVIDER=openai; export OPENAI_API_KEY=...; export OPENAI_BASE_URL=...; export OPENAI_MODEL=...

运行(需联网 api.telegram.org + 所选模型 API)
---------------------------------------------
    uv pip install -e ".[bot]"          # 装 anthropic + openai
    export TELEGRAM_BOT_TOKEN=...        # @BotFather 申请
    export ANTHROPIC_API_KEY=...         # 或按上面切到 deepseek/openai
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
from pathlib import Path
from typing import Any

from .reports_reader import PROJECT_ROOT, ReportNotFound, ReportsReader, normalize_bar, normalize_instrument

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("telegram_bot")

# 智能内核可插拔:BOT_LLM_PROVIDER = claude(默认) | deepseek | openai
# - claude:   anthropic SDK,默认模型 claude-opus-4-8
# - deepseek: OpenAI 兼容,base https://api.deepseek.com,默认 deepseek-chat,key DEEPSEEK_API_KEY
# - openai:   任意 OpenAI 兼容端点,用 OPENAI_BASE_URL / OPENAI_MODEL / OPENAI_API_KEY
PROVIDER = os.environ.get("BOT_LLM_PROVIDER", "claude").strip().lower()
MODEL = "claude-opus-4-8"
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL")  # 必填(自定义兼容端点)
DEFAULT_BAR = "1D"
SUPPORTED_BARS = {"1D", "4H", "8H", "1W"}
STATE_PATH = PROJECT_ROOT / "data" / "telegram_state.json"
POLL_INTERVAL_SEC = int(os.environ.get("BOT_ALERT_INTERVAL_SEC", "900"))  # 盯盘轮询(默认 15 分钟)
BROADCAST_HOUR_UTC = int(os.environ.get("BOT_BROADCAST_HOUR_UTC", "1"))   # 每日播报 UTC 小时(默认 01:00)
HISTORY_TURNS = 12  # 每个会话保留的对话轮数

reader = ReportsReader()

SYSTEM_PROMPT = """你是「市场天气雷达」的播报助手,通过 Telegram 和用户对话。

【你是什么】
雷达是一套**市场状态/环境描述器**:它识别当下更像趋势、震荡还是躁动(高波动)环境,
给出红/黄/绿系灯号代表"此刻适不适合某类策略上场"。它配有概率语境(样本数/置信)。

【铁律——绝对不能违反】
1. 你**只描述当下环境/状态**,**绝不预测涨跌方向**、**绝不给买卖点/目标价/止损**、**绝不喊单或暗示跟单**。
2. 经过严格回测(见结论),雷达**没有已证实的可交易 edge**;方向命中≈基准率。任何"该买/该卖/会涨/会跌"
   的问题,都要明确说明:雷达不预测方向,只能告诉你"现在是什么天气",请用户自行判断、自负盈亏。
3. 概率永远要带样本语境;小样本(样本不足/置信低)必须弱化、提醒别当确定性。
4. 不知道就说不知道;数据缺失就如实说"该品种历史不足/暂无报告",不要编。

【怎么答】
- 用大白话、简洁。需要数据时调用工具实时查,不要凭记忆编数字。
- 解释灯号含义时帮用户理解"环境",而不是"信号"。
- 用户问"现在能不能买/会不会涨"这类,先给环境描述,再用一句话守住红线(不预测方向)。

【工具】
- get_market_weather: 查某品种某周期的当前天气(灯号/环境/状态/概率语境)。
- scan_by_gate: 列出当前处于某灯号的品种。
- market_overview: 某周期下全市场的灯号/状态分布概览。
- list_symbols: 列出所有可查品种。
默认周期 1D。品种用大写如 BTC-USDT。"""

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_market_weather",
        "description": "查某个品种某个周期的当前市场天气:总闸灯号、最像哪类天气、波动/趋势/量能等状态、操作倾向文案、数据状态。只读描述,不含买卖信号。",
        "input_schema": {
            "type": "object",
            "properties": {
                "instrument": {"type": "string", "description": "品种,如 BTC-USDT / ETH-USDT"},
                "bar": {"type": "string", "description": "周期:1D / 4H / 8H / 1W,默认 1D"},
            },
            "required": ["instrument"],
        },
    },
    {
        "name": "scan_by_gate",
        "description": "列出当前处于指定灯号(如 红/黄/绿)的所有品种。用于回答“哪些币现在是 X 灯”。",
        "input_schema": {
            "type": "object",
            "properties": {
                "gate": {"type": "string", "description": "灯号关键字:红 / 黄 / 绿(支持子串匹配,如 黄偏绿)"},
                "bar": {"type": "string", "description": "周期,默认 1D"},
            },
            "required": ["gate"],
        },
    },
    {
        "name": "market_overview",
        "description": "某周期下全市场的灯号分布与波动状态分布概览(各灯号有多少品种)。",
        "input_schema": {
            "type": "object",
            "properties": {"bar": {"type": "string", "description": "周期,默认 1D"}},
            "required": [],
        },
    },
    {
        "name": "list_symbols",
        "description": "列出所有可查询的品种代码。",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]


# --------------------------------------------------------------------------- #
# 工具实现(只读 ReportsReader,返回描述性数据)
# --------------------------------------------------------------------------- #
def _resolve_bar(bar: str | None) -> str:
    norm = normalize_bar(bar) if bar else None
    return norm if norm in SUPPORTED_BARS else DEFAULT_BAR


def resolve_instrument(value: str | None) -> str | None:
    """裸 ticker(如 BTC)自动补成 BTC-USDT;已带 -USDT 的原样归一化。"""
    inst = normalize_instrument(value) if value else None
    if inst and "-" not in inst:
        inst = f"{inst}-USDT"
    return inst


def tool_get_market_weather(instrument: str, bar: str | None = None) -> dict[str, Any]:
    inst = resolve_instrument(instrument) or instrument
    use_bar = _resolve_bar(bar)
    row = reader.current(instrument=inst, bar=use_bar)
    if not row:
        return {"instrument": inst, "bar": use_bar, "status": "no_data", "note": "该品种该周期暂无报告或历史不足"}
    keys = [
        "instrument", "bar", "date", "close", "gate", "topWeatherRoute", "topWeatherScore",
        "weatherSummary", "actionBias", "dataStatus", "periodWeight",
        "volatilityState", "trendState", "volumeState", "remainingMomentumState", "middleState", "maState",
    ]
    out = {k: row.get(k) for k in keys if k in row}
    out["status"] = "ok"
    out["note"] = "只描述当下环境,不含方向预测或买卖信号"
    return out


def tool_scan_by_gate(gate: str, bar: str | None = None) -> dict[str, Any]:
    use_bar = _resolve_bar(bar)
    rows = reader.rows(bar=use_bar)
    matched = [
        {"instrument": r.get("instrument"), "gate": r.get("gate"), "topWeatherRoute": r.get("topWeatherRoute")}
        for r in rows
        if gate in str(r.get("gate") or "")
    ]
    return {"bar": use_bar, "gateQuery": gate, "count": len(matched), "matches": matched[:60]}


def tool_market_overview(bar: str | None = None) -> dict[str, Any]:
    use_bar = _resolve_bar(bar)
    try:
        ov = reader.overview()
    except ReportNotFound:
        return {"status": "no_data"}
    by_bar = (ov.get("byBar") or {}).get(use_bar)
    if not by_bar:
        return {"bar": use_bar, "status": "no_data"}
    return {
        "bar": use_bar,
        "rowCount": by_bar.get("rowCount"),
        "gateCounts": by_bar.get("gateCounts"),
        "volatilityStateCounts": by_bar.get("volatilityStateCounts"),
        "lowWeightCount": by_bar.get("lowWeightCount"),
    }


def tool_list_symbols() -> dict[str, Any]:
    try:
        syms = reader.symbols()
    except ReportNotFound:
        syms = []
    return {"count": len(syms), "symbols": syms}


TOOL_DISPATCH = {
    "get_market_weather": tool_get_market_weather,
    "scan_by_gate": tool_scan_by_gate,
    "market_overview": tool_market_overview,
    "list_symbols": tool_list_symbols,
}


# --------------------------------------------------------------------------- #
# 智能内核(可插拔:Claude / DeepSeek / 任意 OpenAI 兼容端点)
# 工具循环逻辑两边一致;只有"调模型 + 消息格式"不同。
# --------------------------------------------------------------------------- #
_llm_client = None
NO_RESULT = "(没拿到结果,换个问法试试,或用 /help 看命令)"


def _dispatch_tool(name: str, args: dict[str, Any]) -> str:
    fn = TOOL_DISPATCH.get(name)
    try:
        payload = fn(**args) if fn else {"error": f"unknown tool {name}"}
        return json.dumps(payload, ensure_ascii=False)
    except Exception as error:  # noqa: BLE001 - report tool failure to the model
        return json.dumps({"error": str(error)}, ensure_ascii=False)


# ---- Claude(anthropic SDK,手动 agentic loop + prompt caching) ---------- #
def _ask_claude(history: list[dict[str, Any]]) -> str:
    global _llm_client
    if _llm_client is None:
        import anthropic  # 延迟导入

        _llm_client = anthropic.Anthropic()
    system = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
    messages = list(history)
    final = None
    for _ in range(6):
        response = _llm_client.messages.create(
            model=MODEL, max_tokens=2000, thinking={"type": "adaptive"},
            system=system, tools=TOOLS, messages=messages,
        )
        final = response
        if response.stop_reason != "tool_use":
            break
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": _dispatch_tool(block.name, block.input)})
        messages.append({"role": "user", "content": results})
    text = "".join(b.text for b in (final.content if final else []) if b.type == "text").strip()
    return text or NO_RESULT


# ---- DeepSeek / OpenAI 兼容(openai SDK,function calling) -------------- #
def _openai_tools() -> list[dict[str, Any]]:
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["input_schema"]}} for t in TOOLS]


def _openai_config() -> tuple[str, str | None, str, str]:
    """返回 (api_key, base_url, model, env_key_name)。"""
    if PROVIDER == "deepseek":
        return os.environ.get("DEEPSEEK_API_KEY", ""), DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, "DEEPSEEK_API_KEY"
    return os.environ.get("OPENAI_API_KEY", ""), OPENAI_BASE_URL, OPENAI_MODEL, "OPENAI_API_KEY"


def _ask_openai_compatible(history: list[dict[str, Any]]) -> str:
    global _llm_client
    api_key, base_url, model, env_name = _openai_config()
    if not api_key:
        raise RuntimeError(f"missing {env_name}")
    if _llm_client is None:
        from openai import OpenAI  # 延迟导入

        _llm_client = OpenAI(api_key=api_key, base_url=base_url)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
    tools = _openai_tools()
    final_text = ""
    for _ in range(6):
        resp = _llm_client.chat.completions.create(
            model=model, messages=messages, tools=tools, tool_choice="auto", max_tokens=2000,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            final_text = (msg.content or "").strip()
            break
        messages.append({
            "role": "assistant", "content": msg.content or "",
            "tool_calls": [{"id": tc.id, "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                           for tc in msg.tool_calls],
        })
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": _dispatch_tool(tc.function.name, args)})
    return final_text or NO_RESULT


def ask_llm(history: list[dict[str, Any]]) -> str:
    """history: [{role, content}, ...](最后一条为 user)。按 PROVIDER 路由。"""
    if PROVIDER == "claude":
        return _ask_claude(history)
    return _ask_openai_compatible(history)


# --------------------------------------------------------------------------- #
# 状态持久化(订阅 / 盯盘 / 上次灯号)
# --------------------------------------------------------------------------- #
_state_lock = threading.Lock()


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


# --------------------------------------------------------------------------- #
# Telegram HTTP(标准库,零额外依赖)
# --------------------------------------------------------------------------- #
def tg_call(method: str, params: dict[str, Any], timeout: int = 35) -> dict[str, Any]:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def send(chat_id: str | int, text: str) -> None:
    try:
        # Telegram 单条上限 4096
        tg_call("sendMessage", {"chat_id": chat_id, "text": text[:4096]}, timeout=20)
    except Exception as error:  # noqa: BLE001 - a failed send shouldn't kill the loop
        log.warning("sendMessage failed for %s: %s", chat_id, error)


# --------------------------------------------------------------------------- #
# 命令处理
# --------------------------------------------------------------------------- #
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


def fmt_weather(payload: dict[str, Any]) -> str:
    if payload.get("status") != "ok":
        return f"{payload.get('instrument')} {payload.get('bar')}:{payload.get('note', '暂无数据')}"
    return (
        f"📍 {payload.get('instrument')} {payload.get('bar')}  ({payload.get('date')})\n"
        f"总闸:{payload.get('gate')}  |  最像「{payload.get('topWeatherRoute')}」 分 {payload.get('topWeatherScore')}\n"
        f"波动:{payload.get('volatilityState')}  趋势:{payload.get('trendState')}  量能:{payload.get('volumeState')}\n"
        f"{payload.get('weatherSummary') or ''}\n"
        f"倾向:{payload.get('actionBias') or '—'}\n"
        f"(数据 {payload.get('dataStatus')},权重 {payload.get('periodWeight')};只描述环境,不含买卖信号)"
    )


def parse_symbol_bar(args: list[str]) -> tuple[str | None, str]:
    inst = resolve_instrument(args[0]) if args else None
    bar = _resolve_bar(args[1]) if len(args) > 1 else DEFAULT_BAR
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
        bar = _resolve_bar(args[0] if args else None)
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
    # 自然语言 → Claude
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
        history.pop()  # 失败不污染上下文
        send(chat_id, reply)
        return
    history.append({"role": "assistant", "content": reply})
    del history[: max(0, len(history) - HISTORY_TURNS * 2)]  # 裁剪历史
    send(chat_id, reply)


# --------------------------------------------------------------------------- #
# 后台:盯盘告警 + 每日播报
# --------------------------------------------------------------------------- #
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
                            send(cid, f"🔔 灯号翻转 {inst} {bar}:{prev} → {gate}\n"
                                      f"(环境描述变化,非买卖信号)")
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


# --------------------------------------------------------------------------- #
# 主循环:长轮询 getUpdates
# --------------------------------------------------------------------------- #
def main() -> None:
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        raise SystemExit("缺少 TELEGRAM_BOT_TOKEN(@BotFather 申请),见模块文档。")
    key_env = {"claude": "ANTHROPIC_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}.get(PROVIDER, "OPENAI_API_KEY")
    if not os.environ.get(key_env):
        log.warning("未设 %s(provider=%s):命令可用,但自然语言问答会提示配置。", key_env, PROVIDER)
    log.info("LLM provider=%s", PROVIDER)

    histories: dict[str, list] = {}
    threading.Thread(target=alert_loop, daemon=True).start()
    threading.Thread(target=broadcast_loop, daemon=True).start()
    log.info("bot started; long-polling getUpdates")

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
            text = msg["text"]
            try:
                handle_message(chat_id, text, histories)
            except Exception as error:  # noqa: BLE001 - one bad message shouldn't kill the bot
                log.exception("handle_message failed")
                send(chat_id, f"处理出错:{str(error)[:200]}")


if __name__ == "__main__":
    main()
