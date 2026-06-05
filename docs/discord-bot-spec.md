# Discord 机器人:富交互雷达助手(共享大脑)

> 实现 `backend_py/discord_bot.py`,大脑 `backend_py/radar_brain.py`(与 Telegram 共用)。可选依赖 `discord.py`。
> **红线:只描述环境/状态,绝不预测涨跌、不给买卖信号**(对齐 `gate1-conclusion.md`)。

## 架构:一个大脑,两张嘴
```
                ┌──────────── radar_brain.py(共享大脑)───────────┐
                │ SYSTEM_PROMPT(红线) · 4 工具(查 ReportsReader) │
                │ ask_llm(claude/deepseek/openai) · gate_color    │
                └───────────────┬───────────────┬─────────────────┘
                                │               │
                   telegram_bot.py        discord_bot.py
                   (长轮询/命令/盯盘)     (斜杠命令/Embed/NL)
```
换平台只换适配器(嘴),大脑/工具/红线一份。**智能由 LLM 决定,与平台无关——Discord 不比 Telegram 聪明,只是交互更丰富。**

## Discord 的交互优势(已用上)
- **斜杠命令**(带参数补全/下拉):`/weather` `/overview` `/symbols` `/help`。
- **彩色 Embed 卡片**:灯号直接上色(红=#F6465D / 黄=#F0A83C / 黄偏绿=#6FC9A4 / 绿=#2EBD85),字段化排版。
- **自然语言问答**:@机器人 或私信 → Claude/DeepSeek 实时查雷达回答(按频道维护上下文)。

## 命令
| 命令 | 作用 |
|---|---|
| `/weather <品种> [周期]` | 天气 Embed(总闸/最像/波动趋势量能/样本置信/倾向),裸 ticker 自动补 -USDT |
| `/overview [周期]` | 全市场灯号分布 Embed |
| `/symbols` | 可查品种(ephemeral 私密回复) |
| `/help` | 说明 |
| @机器人 / 私信 + 自然语言 | LLM 问答 |

## 智能内核(同 Telegram,可插拔)
`BOT_LLM_PROVIDER = claude(默认) | deepseek | openai`。同步的工具/LLM 调用用 `asyncio.to_thread` 包,不阻塞事件循环。

## 运行
```bash
uv pip install -e ".[bot]"               # 含 discord.py
export DISCORD_BOT_TOKEN=...              # 开发者后台 → Bot → Reset Token
export ANTHROPIC_API_KEY=...             # 或 BOT_LLM_PROVIDER=deepseek + DEEPSEEK_API_KEY
# 可选:export DISCORD_GUILD_ID=<服务器ID>   # 设了斜杠命令即时生效;否则全局~1小时
uv run python -m backend_py.discord_bot
```

## 前置(Discord 后台,全免费、无需会员)
1. https://discord.com/developers/applications → New Application。
2. **Bot → Reset Token** → 复制为 `DISCORD_BOT_TOKEN`(别外泄/别提交)。
3. **开启 Message Content Intent**(自然语言问答要读消息内容)。
4. **OAuth2 → URL Generator**:勾 `bot` + `applications.commands`,权限 `Send Messages`/`Embed Links`/`Use Slash Commands` → 用生成链接邀请进服务器。

## 安全/边界
- 机密只走环境变量,绝不提交;无状态文件(对话上下文仅内存)。
- 不下单、不碰资金;纯只读 + 描述。红线写进共享系统提示,两平台一致。
- 未配模型 key 时:斜杠命令仍可用,自然语言问答优雅提示。

## 验证(本容器)
- `py_compile` 三模块 OK;`radar_brain` 工具实测返回真实数据。
- `discord_bot` import OK,4 斜杠命令注册成功;`telegram_bot` 瘦身后仍 import。
- ⚠️ 端到端(连 Discord 网关)需配 token + 联网,本容器无法实测。
