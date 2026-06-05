"""雷达"大脑":平台无关的智能内核 —— 工具 + 系统提示 + LLM 调用 + 红线。

被 telegram_bot 与 discord_bot 共用。换平台只换"嘴"(适配器),大脑/工具/红线一份。

可插拔 LLM:BOT_LLM_PROVIDER = claude(默认) | deepseek | openai
机密只走环境变量,绝不提交。
"""

from __future__ import annotations

import json
import os
from typing import Any

from .reports_reader import ReportNotFound, ReportsReader, normalize_bar, normalize_instrument

# ---- LLM provider 配置 ---------------------------------------------------- #
PROVIDER = os.environ.get("BOT_LLM_PROVIDER", "claude").strip().lower()
MODEL = "claude-opus-4-8"
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL")

DEFAULT_BAR = "1D"
SUPPORTED_BARS = {"1D", "4H", "8H", "1W"}

reader = ReportsReader()

SYSTEM_PROMPT = """你是「市场天气雷达」的播报助手,通过聊天和用户对话。

【你是什么】
雷达是一套**市场状态/环境描述器**:它识别当下更像趋势、震荡还是躁动(高波动)环境,
给出红/黄/绿系灯号代表"此刻适不适合某类策略上场"。它配有概率语境(样本数/置信)。

【铁律——绝对不能违反】
1. 你**只描述当下环境/状态**,**绝不预测涨跌方向**、**绝不给买卖点/目标价/止损**、**绝不喊单或暗示跟单**。
2. 经过严格回测,雷达**没有已证实的可交易 edge**;方向命中≈基准率。任何"该买/该卖/会涨/会跌"
   的问题,都要明确说明:雷达不预测方向,只能告诉你"现在是什么天气",请用户自行判断、自负盈亏。
3. 概率永远要带样本语境;小样本(样本不足/置信低)必须弱化、提醒别当确定性。
4. 不知道就说不知道;数据缺失就如实说"该品种历史不足/暂无报告",不要编。

【怎么答】
- 用大白话、简洁。需要数据时调用工具实时查,不要凭记忆编数字。
- 解释灯号含义时帮用户理解"环境",而不是"信号"。
- 用户问"现在能不能买/会不会涨"这类,先给环境描述,再用一句话守住红线(不预测方向)。

【工具】
- get_market_weather / scan_by_gate / market_overview / list_symbols。默认周期 1D。品种用大写如 BTC-USDT。"""


# ---- 取数辅助 ------------------------------------------------------------- #
def resolve_bar(bar: str | None) -> str:
    norm = normalize_bar(bar) if bar else None
    return norm if norm in SUPPORTED_BARS else DEFAULT_BAR


def resolve_instrument(value: str | None) -> str | None:
    """裸 ticker(BTC)自动补成 BTC-USDT。"""
    inst = normalize_instrument(value) if value else None
    if inst and "-" not in inst:
        inst = f"{inst}-USDT"
    return inst


# ---- 工具(只读 ReportsReader,只回描述性数据) -------------------------- #
def tool_get_market_weather(instrument: str, bar: str | None = None) -> dict[str, Any]:
    inst = resolve_instrument(instrument) or instrument
    use_bar = resolve_bar(bar)
    row = reader.current(instrument=inst, bar=use_bar)
    if not row:
        return {"instrument": inst, "bar": use_bar, "status": "no_data", "note": "该品种该周期暂无报告或历史不足"}
    keys = [
        "instrument", "bar", "date", "close", "gate", "topWeatherRoute", "topWeatherScore",
        "weatherSummary", "actionBias", "dataStatus", "periodWeight",
        "topWeatherOccurrences", "topWeatherSampleConfidencePct", "topWeatherConfidenceGate",
        "volatilityState", "trendState", "volumeState", "remainingMomentumState", "middleState", "maState",
    ]
    out = {k: row.get(k) for k in keys if k in row}
    out["status"] = "ok"
    out["note"] = "只描述当下环境,不含方向预测或买卖信号"
    return out


def tool_scan_by_gate(gate: str, bar: str | None = None) -> dict[str, Any]:
    use_bar = resolve_bar(bar)
    rows = reader.rows(bar=use_bar)
    matched = [
        {"instrument": r.get("instrument"), "gate": r.get("gate"), "topWeatherRoute": r.get("topWeatherRoute")}
        for r in rows
        if gate in str(r.get("gate") or "")
    ]
    return {"bar": use_bar, "gateQuery": gate, "count": len(matched), "matches": matched[:60]}


def tool_market_overview(bar: str | None = None) -> dict[str, Any]:
    use_bar = resolve_bar(bar)
    try:
        ov = reader.overview()
    except ReportNotFound:
        return {"status": "no_data"}
    by_bar = (ov.get("byBar") or {}).get(use_bar)
    if not by_bar:
        return {"bar": use_bar, "status": "no_data"}
    return {
        "bar": use_bar, "rowCount": by_bar.get("rowCount"),
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
        "description": "列出当前处于指定灯号(如 红/黄/绿)的所有品种。",
        "input_schema": {
            "type": "object",
            "properties": {
                "gate": {"type": "string", "description": "灯号关键字:红 / 黄 / 绿(支持子串,如 黄偏绿)"},
                "bar": {"type": "string", "description": "周期,默认 1D"},
            },
            "required": ["gate"],
        },
    },
    {
        "name": "market_overview",
        "description": "某周期下全市场的灯号分布与波动状态分布概览。",
        "input_schema": {"type": "object", "properties": {"bar": {"type": "string"}}, "required": []},
    },
    {
        "name": "list_symbols",
        "description": "列出所有可查询的品种代码。",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
]

TOOL_DISPATCH = {
    "get_market_weather": tool_get_market_weather,
    "scan_by_gate": tool_scan_by_gate,
    "market_overview": tool_market_overview,
    "list_symbols": tool_list_symbols,
}


# ---- 展示辅助(纯文本 + 灯号颜色) --------------------------------------- #
def fmt_weather(p: dict[str, Any]) -> str:
    if p.get("status") != "ok":
        return f"{p.get('instrument')} {p.get('bar')}:{p.get('note', '暂无数据')}"
    return (
        f"📍 {p.get('instrument')} {p.get('bar')}  ({p.get('date')})\n"
        f"总闸:{p.get('gate')}  |  最像「{p.get('topWeatherRoute')}」 分 {p.get('topWeatherScore')}\n"
        f"波动:{p.get('volatilityState')}  趋势:{p.get('trendState')}  量能:{p.get('volumeState')}\n"
        f"{p.get('weatherSummary') or ''}\n"
        f"倾向:{p.get('actionBias') or '—'}\n"
        f"(数据 {p.get('dataStatus')},权重 {p.get('periodWeight')};只描述环境,不含买卖信号)"
    )


def gate_color(gate: str | None) -> int:
    """灯号 → 颜色(用于 Discord Embed 左色条)。"""
    g = gate or ""
    if "红" in g and "黄" not in g:
        return 0xF6465D
    if "绿" in g and "黄" not in g:
        return 0x2EBD85
    if "黄" in g and "绿" in g:
        return 0x6FC9A4
    if "黄" in g:
        return 0xF0A83C
    return 0x5E6678


# ---- LLM 内核(可插拔:Claude / DeepSeek / OpenAI 兼容) ----------------- #
_llm_client = None
NO_RESULT = "(没拿到结果,换个问法试试)"


def _dispatch_tool(name: str, args: dict[str, Any]) -> str:
    fn = TOOL_DISPATCH.get(name)
    try:
        payload = fn(**args) if fn else {"error": f"unknown tool {name}"}
        return json.dumps(payload, ensure_ascii=False)
    except Exception as error:  # noqa: BLE001
        return json.dumps({"error": str(error)}, ensure_ascii=False)


def _ask_claude(history: list[dict[str, Any]]) -> str:
    global _llm_client
    if _llm_client is None:
        import anthropic

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
        results = [
            {"type": "tool_result", "tool_use_id": b.id, "content": _dispatch_tool(b.name, b.input)}
            for b in response.content if b.type == "tool_use"
        ]
        messages.append({"role": "user", "content": results})
    return "".join(b.text for b in (final.content if final else []) if b.type == "text").strip() or NO_RESULT


def _openai_tools() -> list[dict[str, Any]]:
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["input_schema"]}} for t in TOOLS]


def _openai_config() -> tuple[str, str | None, str, str]:
    if PROVIDER == "deepseek":
        return os.environ.get("DEEPSEEK_API_KEY", ""), DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, "DEEPSEEK_API_KEY"
    return os.environ.get("OPENAI_API_KEY", ""), OPENAI_BASE_URL, OPENAI_MODEL, "OPENAI_API_KEY"


def _ask_openai_compatible(history: list[dict[str, Any]]) -> str:
    global _llm_client
    api_key, base_url, model, env_name = _openai_config()
    if not api_key:
        raise RuntimeError(f"missing {env_name}")
    if _llm_client is None:
        from openai import OpenAI

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
    """history: [{role, content}, ...](最后一条 user)。按 PROVIDER 路由。"""
    if PROVIDER == "claude":
        return _ask_claude(history)
    return _ask_openai_compatible(history)


def provider_key_env() -> str:
    return {"claude": "ANTHROPIC_API_KEY", "deepseek": "DEEPSEEK_API_KEY"}.get(PROVIDER, "OPENAI_API_KEY")
