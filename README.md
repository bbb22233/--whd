# Quant Monitor Terminal

这是独立的加密市场天气研究项目，当前主线是 BTC-USDT 现货日线。

系统目标不是直接给买卖点，而是识别市场天气和策略适配度：

- ATR / 振幅 / 剩余动能负责波动天气。
- 中值乖离负责短期拉伸和回归。
- 233MA 乖离负责大周期天气过滤。
- 决策树、SOM、宏观因子用于辅助解释和验证。

## 常用命令

```bash
npm run download -- --instrument BTC-USDT --days 3650
npm run clean -- --instrument BTC-USDT --days 3650
npm run weather:router -- --instrument BTC-USDT --days 3650
```

## Python API

Python API 是前端数据源迁移的桥接层,读取现有 `reports/` 和 `data/clean/` 产物,不替代当前 Node 研究流水线。

```bash
uv sync
uv run uvicorn backend_py.main:app --host 127.0.0.1 --port 8000
```

验证:

```bash
uv run python -m backend_py.smoke_test
curl -fsS http://127.0.0.1:8000/health
curl -fsS "http://127.0.0.1:8000/api/dashboard/current?instrument=BTC-USDT&bar=1D"
```

## 当前主线输出

```text
reports/*_market_weather_current.csv              当前市场天气
reports/*_market_weather_scores.csv               策略天气适配分数
reports/*_market_weather_components_current.csv   当前波动组件概率
reports/*_market_weather_router.json              完整天气路由结果
```

## 位置指标研究

```bash
npm run backtest:deviations -- --instrument BTC-USDT --days 3650
npm run rules:deviations -- --instrument BTC-USDT --days 3650
```

核心输出：

```text
reports/*_deviation_current.csv          当前中值/233MA 乖离状态
reports/*_deviation_state_summary.csv    位置状态历史概率
reports/*_deviation_rules_current.csv    当前位置规则结论
reports/*_deviation_rule_library.csv     位置规则库
```

## 神经网络与决策树

```bash
npm run train:state -- --instrument BTC-USDT --days 3650
npm run train:trees -- --instrument BTC-USDT --days 3650
npm run validate:trees -- --instrument BTC-USDT --days 3650 --train-to 2023-12-31 --validate-from 2024-01-01
```

宏观对比：

```bash
npm run download:macro -- --instrument BTC-USDT --days 3650
npm run train:trees -- --instrument BTC-USDT --days 3650 --macro
npm run compare:macro -- --instrument BTC-USDT --days 3650 --train-to 2023-12-31 --validate-from 2024-01-01
```

## 数据与归档

```text
data/raw/       OKX 原始数据
data/clean/     清洗后的 K 线数据
data/macro/     宏观特征数据
reports/        当前轻量报告和 summary
reports/archive 历史大 CSV 明细，可按需恢复或重生成
```

旧前端原型、旧 label 回测、旧 pipeline 入口已经清理。后续前端应直接读取 `market_weather` 和 `deviation_rules` 输出。
