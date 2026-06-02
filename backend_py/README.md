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
POST /api/scanner/run?mode=python_summary
POST /api/scanner/run?mode=python_summary&symbols=BTC-USDT,ETH-USDT&bars=1D,4H
POST /api/scanner/run?mode=python_router
POST /api/scanner/run?mode=python_router&symbols=BTC-USDT,ETH-USDT&bars=1D,4H
POST /api/scanner/run?mode=python_research
POST /api/scanner/run?mode=python_research&symbols=BTC-USDT,ETH-USDT&bars=1D,4H
POST /api/scanner/run?mode=python_data
POST /api/scanner/run?mode=python_data&symbols=BTC-USDT,ETH-USDT&bars=1D,4H
POST /api/scanner/run?mode=full
POST /api/scanner/cancel
```

扫描模式：

- `summary`: 调用现有 Node 脚本从已有 reports 重建多周期汇总，不下载。
- `python_summary`: 调用 Python from-reports summary parity 路径,默认跑 `BTC-USDT 1D`,可用 `symbols`/`bars` 参数扩大范围,只写 `_py` 对照产物。
- `python_router`: 调用 Python 完整 router parity 路径,默认跑 `BTC-USDT 1D`,可用 `symbols`/`bars` 参数扩大范围,只写 `_py` 对照产物并对比现有 Node reports。
- `python_research`: 调用 Python feature/deviation/router/summary parity 链路,默认跑 `BTC-USDT 1D`,可用 `symbols`/`bars` 参数扩大范围,只写 `_py` 对照产物;如果现有 Node golden 日期或汇总范围不匹配,对应 compare 会标记为 skipped,不会重写 Node 正式报告。
- `python_data`: 调用 Python OKX download + clean 数据入口,默认跑 `BTC-USDT 1D`,可用 `symbols`/`bars` 参数扩大范围,会写入 `data/raw` 与 `data/clean`。
- `full`: 调用现有 Node 多周期扫描，会尝试下载/刷新数据。

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

- 现在仍由 Node 脚本负责下载、清洗、扫描、训练和生成 reports。
- Python 先负责读取 reports 并对前端提供 API。
- 后续再把实时扫描调度、模型推理、训练研究逐步迁移进 Python。
