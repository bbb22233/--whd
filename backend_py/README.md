# Python Backend

第一阶段迁移只接管 API 层，不重写现有 Node 扫描流水线。

当前 Python 后端读取：

```text
reports/multi_period_market_weather_current.json
```

## 启动

推荐用根目录的 `pyproject.toml` 复现环境:

```bash
uv sync
uv run uvicorn backend_py.main:app --host 127.0.0.1 --port 8000
```

也可以用系统 Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend_py/requirements.txt
python -m uvicorn backend_py.main:app --host 127.0.0.1 --port 8000
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend_py/requirements.txt
python -m uvicorn backend_py.main:app --host 127.0.0.1 --port 8000
```

## API

```text
GET /health
GET /api/market/metadata
GET /api/market/overview
GET /api/market/symbols
GET /api/market/rows?bar=4H
GET /api/market/current/BTC-USDT?bar=4H
GET /api/reports/BTC_USDT_1D_market_weather_router.json
GET /api/candles/BTC-USDT/1D
GET /api/dashboard/current?instrument=BTC-USDT&bar=1D
GET /api/scanner/status
POST /api/scanner/run?mode=summary
POST /api/scanner/run?mode=node_summary
POST /api/scanner/run?mode=python_summary
POST /api/scanner/run?mode=python_summary&symbols=BTC-USDT,ETH-USDT&bars=1D,4H
POST /api/scanner/run?mode=python_router
POST /api/scanner/run?mode=python_router&symbols=BTC-USDT,ETH-USDT&bars=1D,4H
POST /api/scanner/run?mode=python_research
POST /api/scanner/run?mode=python_research&symbols=BTC-USDT,ETH-USDT&bars=1D,4H
POST /api/scanner/run?mode=python_data
POST /api/scanner/run?mode=python_data&symbols=BTC-USDT,ETH-USDT&bars=1D,4H
POST /api/scanner/run?mode=python_full
POST /api/scanner/run?mode=python_full&symbols=BTC-USDT,ETH-USDT&bars=1D,4H
POST /api/scanner/run?mode=full
POST /api/scanner/run?mode=node_full
POST /api/scanner/cancel
```

扫描模式：

- `summary`: 调用 Python official summary-only pipeline,从已有正式 reports 重建正式多周期汇总,默认范围为 58 个 symbols × `1D,4H,8H`,不下载。
- `full`: 调用 Python official full pipeline,默认使用本地 `data/raw` 与 `data/clean` 生成正式 `reports/`,默认范围为 58 个 symbols × `1D,4H,8H`;可用 `symbols`/`bars` 参数缩小范围。
- `node_summary`: 调用 legacy Node from-reports summary rebuild,作为回退入口保留。
- `node_full`: 调用 legacy Node 多周期扫描，会尝试下载/刷新数据,作为回退入口保留。
- `python_summary`: 调用 Python from-reports summary parity 路径,默认跑 `BTC-USDT 1D`,可用 `symbols`/`bars` 参数扩大范围,只写 `_py` 对照产物。
- `python_router`: 调用 Python 完整 router parity 路径,默认跑 `BTC-USDT 1D`,可用 `symbols`/`bars` 参数扩大范围,只写 `_py` 对照产物并对比现有 Node reports。
- `python_research`: 调用 Python feature/deviation/router/summary parity 链路,默认跑 `BTC-USDT 1D`,可用 `symbols`/`bars` 参数扩大范围,只写 `_py` 对照产物;如果现有 Node golden 日期或汇总范围不匹配,对应 compare 会标记为 skipped,不会重写 Node 正式报告。
- `python_data`: 调用 Python OKX download + clean 数据入口,默认跑 `BTC-USDT 1D`,可用 `symbols`/`bars` 参数扩大范围,会写入 `data/raw` 与 `data/clean`。
- `python_full`: 调用 Python download/clean/research/summary 完整编排器,默认跑 `BTC-USDT 1D`,可用 `symbols`/`bars` 参数扩大范围;默认写 `_py_full` 对照 reports,CLI 加 `--official` 后才写正式 report 名称。

全量跑 `python_full` 前可先检查本地输入覆盖:

```bash
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
```

正式写入 report 名称前可先查看输出计划,不覆盖任何文件:

```bash
uv run python -m backend_py.run_full_pipeline --plan-outputs --official --skip-download --bars 1D,4H,8H --days 3650
```

分批补齐缺失 raw/clean 可用:

```bash
uv run python -m backend_py.run_data_pipeline --missing-only --symbols SOL-USDT BNB-USDT XRP-USDT DOGE-USDT ADA-USDT --bars 1D,4H --days 3650
```

## 验证

```bash
uv run python -m backend_py.smoke_test
uv run python -m backend_py.compare_clean_data --instrument BTC-USDT --bar 1D --days 3650
node --check app.js
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/market/overview
curl -fsS "http://127.0.0.1:8000/api/dashboard/current?instrument=BTC-USDT&bar=1D"
```

`data/clean/` 不进 Git。干净 clone 中 smoke test 会把 clean candles 标记为 `missing_untracked_data`;跑过 `npm run download` + `npm run clean` 后会变为 `ok`。
Dashboard API 会把 `data/clean/` 作为可选源:缺少 clean candles 时仍返回 200,`candles` 为 `null`,前端继续渲染 reports 中的研究结果。

## 迁移边界

- 现在 `summary` 与 `full` scanner 入口已切到 Python official pipeline,正式 reports 与 summaries 由 Python 生成。
- legacy Node scanner 暂时保留为 `node_summary` / `node_full` 回退入口。
- Python 先负责读取 reports 并对前端提供 API。
- 后续再把实时扫描调度、模型推理、训练研究逐步迁移进 Python,并在确认无回退需求后移除 Node 生产路径。
