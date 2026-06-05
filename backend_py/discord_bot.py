"""市场天气雷达 · Discord 适配器(大脑见 radar_brain)。

发挥 Discord 优势:斜杠命令 + 彩色 Embed 卡片 + 自然语言问答(@机器人 或私信)。
大脑/工具/红线与 Telegram 共用一份 —— 只描述环境/状态,绝不预测涨跌、不给买卖信号。

运行(需联网 Discord 网关 + 所选模型 API)
    uv pip install -e ".[bot]"
    export DISCORD_BOT_TOKEN=...          # Discord 开发者后台 → Bot → Reset Token
    export ANTHROPIC_API_KEY=...          # 或 BOT_LLM_PROVIDER=deepseek + DEEPSEEK_API_KEY
    # 可选:DISCORD_GUILD_ID=<服务器ID>   # 设了则斜杠命令在该服务器即时生效(否则全局,需~1小时)
    uv run python -m backend_py.discord_bot

前置:在开发者后台开启 "Message Content Intent"(自然语言问答要读消息);
邀请时勾 bot + applications.commands,权限 Send Messages / Embed Links / Use Slash Commands。
机密只走环境变量,绝不提交。
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import discord
from discord import app_commands

from .radar_brain import (
    PROVIDER,
    ask_llm,
    gate_color,
    provider_key_env,
    tool_get_market_weather,
    tool_list_symbols,
    tool_market_overview,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("discord_bot")

HISTORY_TURNS = 12
DISCLAIMER = "雷达只描述当下环境/状态,不预测涨跌、不给买卖信号。盈亏自负。"
BAR_CHOICES = [app_commands.Choice(name=b, value=b) for b in ("1D", "4H", "8H", "1W")]

_histories: dict[str, list[dict[str, Any]]] = {}

intents = discord.Intents.default()
intents.message_content = True  # 自然语言问答需要(后台须开启 Message Content Intent)
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# ---- Embed 构造 ----------------------------------------------------------- #
def weather_embed(p: dict[str, Any]) -> discord.Embed:
    if p.get("status") != "ok":
        return discord.Embed(
            title=f"{p.get('instrument')} {p.get('bar')}",
            description=p.get("note", "暂无数据"),
            color=0x5E6678,
        )
    e = discord.Embed(
        title=f"📍 {p.get('instrument')} · {p.get('bar')}",
        description=p.get("weatherSummary") or "—",
        color=gate_color(p.get("gate")),
    )
    e.add_field(name="总闸", value=str(p.get("gate") or "—"), inline=True)
    e.add_field(name="最像", value=f"{p.get('topWeatherRoute') or '—'} · {p.get('topWeatherScore')}", inline=True)
    e.add_field(name="日期", value=str(p.get("date") or "—"), inline=True)
    e.add_field(name="波动", value=str(p.get("volatilityState") or "—"), inline=True)
    e.add_field(name="趋势", value=str(p.get("trendState") or "—"), inline=True)
    e.add_field(name="量能", value=str(p.get("volumeState") or "—"), inline=True)
    occ = p.get("topWeatherOccurrences")
    conf = p.get("topWeatherSampleConfidencePct")
    gateword = p.get("topWeatherConfidenceGate")
    e.add_field(name="样本/置信", value=f"{occ if occ is not None else '--'}次 · {conf if conf is not None else '--'}% · {gateword or '--'}", inline=False)
    if p.get("actionBias"):
        e.add_field(name="倾向", value=str(p.get("actionBias")), inline=False)
    e.set_footer(text=DISCLAIMER)
    return e


def overview_embed(ov: dict[str, Any], bar: str) -> discord.Embed:
    if ov.get("status") == "no_data" or not ov.get("gateCounts"):
        return discord.Embed(title=f"{bar} 概览", description="暂无概览数据", color=0x5E6678)
    gc = ov.get("gateCounts") or {}
    lines = "\n".join(f"`{g:<6}` {n}" for g, n in gc.items())
    e = discord.Embed(
        title=f"🗺️ {bar} 全市场灯号分布",
        description=lines,
        color=0x5CC8FF,
    )
    e.add_field(name="品种数", value=str(ov.get("rowCount") or "--"), inline=True)
    e.set_footer(text="只描述环境分布,不含买卖信号")
    return e


# ---- 斜杠命令 ------------------------------------------------------------- #
@tree.command(name="weather", description="查某品种某周期的当前市场天气(只描述环境,不含买卖信号)")
@app_commands.describe(instrument="品种,如 BTC 或 BTC-USDT", bar="周期(默认 1D)")
@app_commands.choices(bar=BAR_CHOICES)
async def weather_cmd(interaction: discord.Interaction, instrument: str, bar: app_commands.Choice[str] | None = None):
    bar_v = bar.value if bar else "1D"
    await interaction.response.defer()
    p = await asyncio.to_thread(tool_get_market_weather, instrument, bar_v)
    await interaction.followup.send(embed=weather_embed(p))


@tree.command(name="overview", description="某周期下全市场的灯号分布概览")
@app_commands.describe(bar="周期(默认 1D)")
@app_commands.choices(bar=BAR_CHOICES)
async def overview_cmd(interaction: discord.Interaction, bar: app_commands.Choice[str] | None = None):
    bar_v = bar.value if bar else "1D"
    await interaction.response.defer()
    ov = await asyncio.to_thread(tool_market_overview, bar_v)
    await interaction.followup.send(embed=overview_embed(ov, bar_v))


@tree.command(name="symbols", description="列出所有可查询的品种")
async def symbols_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    data = await asyncio.to_thread(tool_list_symbols)
    syms = data.get("symbols") or []
    text = f"共 {len(syms)} 个品种:\n" + ", ".join(syms[:120]) if syms else "暂无品种数据"
    await interaction.followup.send(text[:2000], ephemeral=True)


@tree.command(name="help", description="使用说明")
async def help_cmd(interaction: discord.Interaction):
    e = discord.Embed(
        title="📡 市场天气雷达机器人",
        description=(
            "我只描述当下市场环境/状态,**不预测涨跌、不给买卖信号**。\n\n"
            "**斜杠命令**\n"
            "`/weather <品种> [周期]` 查天气\n"
            "`/overview [周期]` 全市场灯号分布\n"
            "`/symbols` 可查品种\n\n"
            "**自然语言**:@我 或私信我,直接问「BTC 现在什么天气」「哪些币绿灯」。"
        ),
        color=0x5CC8FF,
    )
    e.set_footer(text=DISCLAIMER)
    await interaction.response.send_message(embed=e, ephemeral=True)


# ---- 自然语言问答(@机器人 或私信) ------------------------------------ #
@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    is_dm = message.guild is None
    mentioned = client.user is not None and client.user in message.mentions
    if not (is_dm or mentioned):
        return

    content = message.content
    if client.user is not None:
        content = content.replace(f"<@{client.user.id}>", "").replace(f"<@!{client.user.id}>", "")
    content = content.strip()
    if not content:
        return

    key = str(message.channel.id)
    history = _histories.setdefault(key, [])
    history.append({"role": "user", "content": content})
    try:
        async with message.channel.typing():
            reply = await asyncio.to_thread(ask_llm, history)
    except Exception as error:  # noqa: BLE001 - surface LLM/config errors
        log.exception("ask_llm failed")
        msg = str(error)
        history.pop()
        if "API_KEY" in msg.upper() or "api_key" in msg.lower():
            reply = f"智能问答需要配置模型 API key(provider={PROVIDER})。斜杠命令仍可用。"
        else:
            reply = f"出错了:{msg[:300]}"
        await message.reply(reply[:2000])
        return
    history.append({"role": "assistant", "content": reply})
    del history[: max(0, len(history) - HISTORY_TURNS * 2)]
    await message.reply(reply[:2000])


@client.event
async def on_ready():
    guild_id = os.environ.get("DISCORD_GUILD_ID")
    try:
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            tree.copy_global_to(guild=guild)
            await tree.sync(guild=guild)
            log.info("slash commands synced to guild %s", guild_id)
        else:
            await tree.sync()
            log.info("slash commands synced globally (may take up to ~1h to appear)")
    except Exception as error:  # noqa: BLE001
        log.warning("command sync failed: %s", error)
    log.info("discord bot ready as %s; LLM provider=%s", client.user, PROVIDER)


def main() -> None:
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit("缺少 DISCORD_BOT_TOKEN(开发者后台 → Bot → Reset Token),见模块文档。")
    if not os.environ.get(provider_key_env()):
        log.warning("未设 %s(provider=%s):斜杠命令可用,但自然语言问答会提示配置。", provider_key_env(), PROVIDER)
    client.run(token, log_handler=None)


if __name__ == "__main__":
    main()
