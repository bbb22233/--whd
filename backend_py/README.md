# Python Backend

第一阶段迁移只接管 API 层，不重写现有 Node 扫描流水线。

当前 Python 后端读取：

```text
reports/multi_period_market_weather_current.json
```

## 启动

```powershell
python -m uvicorn backend_py.main:app --host 127.0.0.1 --port 8000
```

如果本机没有把 Python 加入 PATH，可使用 Codex 工作区运行时：

```powershell
& 'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m uvicorn backend_py.main:app --host 127.0.0.1 --port 8000
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
GET /api/scanner/status
POST /api/scanner/run?mode=summary
POST /api/scanner/run?mode=full
POST /api/scanner/cancel
```

扫描模式：

- `summary`: 调用现有 Node 脚本从已有 reports 重建多周期汇总，不下载。
- `full`: 调用现有 Node 多周期扫描，会尝试下载/刷新数据。

## 验证

```powershell
python -m backend_py.smoke_test
```

## 迁移边界

- 现在仍由 Node 脚本负责下载、清洗、扫描、训练和生成 reports。
- Python 先负责读取 reports 并对前端提供 API。
- 后续再把实时扫描调度、模型推理、训练研究逐步迁移进 Python。
