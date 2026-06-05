# 实时监控:WebSocket 增量接入(做对的版本)

> 解决"数据冻结 → 监控/灯号提醒不响"的根问题。**历史只回填一次,之后只接新收盘bar**,不重下全量。

## 为什么不用"每轮重下"
- `live_refresh.py`(旧):每轮 `下载全量3650天 + 重算` —— 蠢:重复拉不变的历史、慢、撞 OKX 限频。**仅作回退/cron 用。**
- `ws_monitor.py`(对):OKX WebSocket 订阅蜡烛频道,**只在收到 `confirm="1"`(已收盘)的新bar时**追加 + 增量重算。几乎不耗网络。

## 数据流(无历史重下)
```
OKX WS candle 频道 ──收盘bar──▶ 追加 data/raw ──▶ 重清洗(--clean-only,不下载)
    ──▶ 重算官方报告(--skip-download --official)──▶ 机器人盯盘/前端读到新灯号
```
复用现有清洗/报告逻辑,只新增 WS 接入 + 追加一根 raw。

## 对齐(关键)
- OKX 原生蜡烛:`1D / 4H / 1W`;**`8H` 非原生,由 4H 聚合**。故订阅原生 `1D/4H/1W`,4H 收盘时官方产线连带重算 8H。
- WS 频道名 = `candle` + REST 的 bar 串(`candle1D`/`candle4H`),与下载历史时同一周期边界,保证增量bar和历史无缝衔接。
- 去重:同一根收盘bar OKX 可能多推,按 openTime 去重;收盘值覆盖之前的未收盘值。

## 雷达层 vs 行情层
- **雷达层(本模块)**:灯号按**收盘K线**更新(防偷看)——1D 约一天、4H 每 4 小时、8H 每 8 小时、1W 每周。WS 让"新收盘"**秒级**被感知并重算。
- **行情层(现价)**:若要秒级现价,另订阅 `tickers` 频道直推前端(本模块未含,可加)。雷达灯号不逐 tick 跳(那是错的)。

## 运行
```bash
uv pip install -e ".[live]"          # 装 websockets
# 前置:先回填一次历史,让 data/raw 存在
uv run python -m backend_py.run_data_pipeline --symbols BTC-USDT ETH-USDT --bars 1D,4H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --official --symbols BTC-USDT ETH-USDT --bars 1D,4H,8H --days 3650
# 起实时监控
WS_MONITOR_SYMBOLS=BTC-USDT,ETH-USDT WS_MONITOR_BARS=1D,4H,8H uv run python -m backend_py.ws_monitor
# 或 systemd:cp deploy/whd-ws.service /etc/systemd/system/ && systemctl enable --now whd-ws
```
配合机器人盯盘 loop(每 15 分钟读报告)→ 灯号翻转近实时推送。

## 验证(本容器)
- `py_compile` OK;`websockets 16.0` 可装。
- 原生/派生映射(8H→订阅4H+派生)、订阅频道构造、`append_raw_row` 去重/排序 —— 离线实测正确。
- ⚠️ WS 实连 OKX 需联网(本容器 OKX 被封),端到端要在联网机器上跑;前置须先回填历史(data/raw 存在)。
