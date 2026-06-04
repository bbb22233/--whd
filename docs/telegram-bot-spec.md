# Telegram 机器人:Claude 驱动的雷达对话/盯盘助手

> 实现:`backend_py/telegram_bot.py`(可选依赖 `anthropic`,装法 `uv pip install -e ".[bot]"`)。基线 `main`。
> **贯穿红线:机器人只描述当下市场环境/状态,绝不预测涨跌、不给买卖信号、不喊单**(对齐 `gate1-conclusion.md` 的收手定位)。

## 1. 四项能力(都已实现)
| 能力 | 怎么用 | 实现 |
|---|---|---|
| **自然语言问答** | 直接发问:「BTC 现在什么天气」「哪些币绿灯」 | Claude `opus-4-8` + 工具,手动 agentic loop,实时查 `ReportsReader` |
| **主动盯盘推送** | `/watch BTC 1D` → 灯号翻转时 @你 | 后台线程每 15 分钟轮询,对比上次灯号,变了就推 |
| **定时播报** | `/daily on` → 每日固定时刻推关注品种概览 | 后台线程,UTC 小时触发 |
| **按需命令** | `/weather` `/overview` 等,秒回、零 LLM | 直接调工具,不走 Claude |

## 2. 智能内核(可插拔:Claude / DeepSeek / OpenAI 兼容)
**一个环境变量切换** `BOT_LLM_PROVIDER`:工具循环逻辑两边一致,只换"调模型 + 消息格式"层。

| provider | key | 默认模型 | 说明 |
|---|---|---|---|
| `claude`(默认) | `ANTHROPIC_API_KEY` | `claude-opus-4-8` | 最智能;adaptive thinking + prompt caching |
| `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-chat` | **更便宜**;OpenAI 兼容(`https://api.deepseek.com`),function calling |
| `openai` | `OPENAI_API_KEY` | `gpt-4o-mini` | 任意 OpenAI 兼容端点,配 `OPENAI_BASE_URL` / `OPENAI_MODEL` |

- **工具**(只读 `ReportsReader`,只回描述性数据,两 provider 共用):`get_market_weather` / `scan_by_gate` / `market_overview` / `list_symbols`。
- Claude 路径:手动 agentic loop + `system` 块 `cache_control:ephemeral` 缓存 tools+system 前缀。
- DeepSeek/OpenAI 路径:`chat.completions` + function calling,工具 schema 自动转 OpenAI 格式。
- **红线写进系统提示(两 provider 同一份)**:任何"该买/会涨"类问题,先给环境描述,再守住"雷达不预测方向"。

## 3. 命令
```
/weather <品种> [周期]   查天气(如 /weather BTC 1D;裸 ticker 自动补 -USDT)
/overview [周期]         全市场灯号分布
/watch <品种> [周期]     盯盘,灯号翻转提醒
/unwatch <品种> [周期]   取消盯盘
/watchlist               我的盯盘列表
/daily on|off            每日播报开关
/reset                   清空对话上下文
/help                    帮助
```

## 4. 机密与状态
- **机密只走环境变量,绝不提交**:`TELEGRAM_BOT_TOKEN`(@BotFather)、`ANTHROPIC_API_KEY`(Anthropic 控制台)。
- 状态(订阅/盯盘/上次灯号)存 `data/telegram_state.json`——`data/` 已在 `.gitignore`,不入库。
- 未设 `ANTHROPIC_API_KEY` 时:命令仍可用,自然语言问答提示去配置(优雅降级)。

## 5. 运行
```bash
uv pip install -e ".[bot]"            # 装 anthropic + openai(可选依赖)
export TELEGRAM_BOT_TOKEN=...

# 选一个内核:
# (默认 claude)
export ANTHROPIC_API_KEY=...
# 或 DeepSeek(更便宜):
#   export BOT_LLM_PROVIDER=deepseek && export DEEPSEEK_API_KEY=...
# 或任意 OpenAI 兼容端点:
#   export BOT_LLM_PROVIDER=openai && export OPENAI_API_KEY=... && export OPENAI_BASE_URL=... && export OPENAI_MODEL=...

# 可选:BOT_ALERT_INTERVAL_SEC(默认 900)/ BOT_BROADCAST_HOUR_UTC(默认 1)
uv run python -m backend_py.telegram_bot
```
联网要求:`api.telegram.org`(长轮询 getUpdates)+ 所选模型 API(Anthropic 或 DeepSeek/OpenAI)。数据来自已生成的 `reports/`。

## 6. 调参建议(成本/体验)
- 盯盘灯号只在报告刷新时变化,`BOT_ALERT_INTERVAL_SEC` 与数据刷新频率对齐即可(默认 15 分钟足够)。
- 想省钱:把 `MODEL` 改 `claude-sonnet-4-6`,或常见查询多走命令(零 LLM)。
- prompt caching 已开,多轮对话/重复前缀能省 token。

## 7. 边界(不做什么)
- 不下单、不接交易所私钥、不碰资金——**纯只读 + 描述**。
- 不预测方向、不给点位。任何"信号化"措辞都被系统提示拦住。
- 不读 calibration 内部产物;只读 official 报告的描述性字段。

## 8. 验证(本地,无需 API/网络的部分)
- `uv run python -m py_compile backend_py/telegram_bot.py` 过。
- 工具实测(读已提交报告):`tool_get_market_weather('BTC','1D')`、`scan_by_gate('绿','1D')`、`market_overview('1D')`、`list_symbols()` 均返回真实数据。
- 端到端(发消息/盯盘/问答)需在配好两个 env + 联网的环境跑。
