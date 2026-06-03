# Remaining Node Command Inventory

本文件记录 Python official + frozen golden cutover 后仍保留的 Node package scripts。

## Current Boundary

生产报告生成、数据下载/清洗、研究报告、router backtest/calibration、macro download 与一键 parity 回归均已切到 Python。

`backend_py.run_parity_check --golden` 使用 `tests/fixtures/data/clean` + `tests/golden` 作为冻结标准答案,不再需要现场运行 Node research code。

## Retained Runtime Utility

| Script | Node target | Status |
| --- | --- | --- |
| `serve` | `server.mjs` | 保留。它只服务静态前端文件,不参与研究报告生成。 |

## Removed Node Package Entrypoints

以下 package scripts 已从 `package.json` 移除:

- `legacy:*`
- `backtest:indicators`
- `backtest:volatility`
- `backtest:position`
- `backtest:deviations`
- `journal:create`
- `train:*`
- `validate:trees`
- `compare:macro`

## Verification

- `backend_py.smoke_test` 断言 `package.json` 中以 `node ` 开头的 script 只剩 `serve`。
- `backend_py.run_parity_check --golden` 是后续不依赖 Node research code 的固定回归入口。
