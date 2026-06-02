# REST Dashboard API 施工规格

> 目标:把前端详情页的数据主路径从“直接读多个本地 JSON 文件”迁到“读取一个 Python REST dashboard endpoint”。这是架构迁移的第二步:Python API 成为前端数据边界,`reports/` 与 `data/clean/` 退到后端内部存储。

## 1. 范围

本轮只做桥接层,不重写 Node 研究流水线。

- Python 新增聚合接口:
  - `GET /api/dashboard/current?instrument=BTC-USDT&bar=1D`
- 前端主路径改为读取该接口。
- 保留现有静态文件 fallback,仅作为 API 不可用时的降级。
- 不改报告生成算法、不改 `reports/` 文件结构、不改 UI 视觉布局。

## 2. API 契约

请求:

```text
GET /api/dashboard/current?instrument=BTC-USDT&bar=1D
```

响应:

```json
{
  "instrument": "BTC-USDT",
  "bar": "1D",
  "sources": {
    "weather": {"status": "ok", "name": "BTC_USDT_1D_market_weather_router.json"},
    "features": {"status": "ok", "name": "BTC_USDT_1D_feature_factory.json"},
    "deviations": {"status": "ok", "name": "BTC_USDT_1D_deviation_rules.json"},
    "candles": {"status": "ok", "name": "BTC_USDT_1D_clean.json"}
  },
  "weather": {},
  "features": {},
  "deviations": {},
  "candles": {}
}
```

字段规则:

- `instrument` 使用 `normalize_instrument`,支持 `BTC-USDT`、`BTC_USDT`、`BTCUSDT`。
- `bar` 使用 `normalize_bar`,支持 `1D`、`4H`、`8H`、`1W`。
- `weather`、`features` 为必需;缺失返回 HTTP 404。
- `deviations` 为可选;缺失时为 `null`,且 `sources.deviations.status = "missing_optional"`。
- `candles` 为可选;缺失时为 `null`,且 `sources.candles.status = "missing_optional"`。前端必须可渲染无 K 线状态,不能整页加载失败。
- 任何非法 `instrument/bar` 返回 HTTP 400。

## 3. 文件责任

API 侧:

- `backend_py/reports_reader.py`
  - 新增 `report_stem(instrument, bar)` 或等价 helper。
  - 新增 `load_dashboard(instrument, bar)` 聚合 weather/features/deviations/candles。
  - 不改变现有 `load_json_report`、`load_clean_candles` 的外部行为。

- `backend_py/main.py`
  - 新增 `GET /api/dashboard/current`。
  - 只做 HTTP 错误映射,业务读取委托给 `ReportsReader`。

- `backend_py/smoke_test.py`
  - 增加 dashboard endpoint/helper 覆盖。
  - clean data 缺失仍应降级,不能让干净 clone smoke test 失败。

前端侧:

- `app.js`
  - 新增 `dashboard` API source。
  - `renderDashboard` 优先读取 dashboard payload。
  - dashboard API 失败时 fallback 到现有四文件读取逻辑。
  - `candles` 为 `null` 时仍渲染天气、特征、规则;价格网格显示 `--`,不抛错。

文档侧:

- `README.md` / `backend_py/README.md`
  - 补 dashboard endpoint 启动与 curl 验证。

- `docs/verification-log.md`
  - 补本轮验证记录。

## 4. 验证命令

```bash
uv run python -m backend_py.smoke_test
node --check app.js
node --check server.mjs
uv run python -m py_compile backend_py/*.py
```

启动 API 后:

```bash
curl -fsS "http://127.0.0.1:8000/api/dashboard/current?instrument=BTC-USDT&bar=1D" \
  | python3 -c 'import json,sys; p=json.load(sys.stdin); print(p["instrument"], p["bar"], p["sources"]["weather"]["status"], p["sources"]["candles"]["status"])'
```

启动前端后:

```bash
curl -I http://127.0.0.1:4177/
```

## 5. 验收标准

- dashboard API 返回 200,包含 `weather/features/deviations/candles` 四个顶层字段。
- 干净 clone 或缺少 `data/clean` 时 dashboard API 仍返回 200,`candles=null`。
- 前端 API 主路可用时只需一次 dashboard fetch 即可渲染主页面。
- Python API 未启动时,前端仍 fallback 到旧静态路径。
- 所有语法/smoke test 通过。
