# Remaining Node Command Inventory

本文件记录 Python official cutover 后仍保留的 Node package scripts。目标是让剩余 JavaScript/Node 入口的用途、风险和迁移顺序清晰可查。

## Current Boundary

生产主路径已切到 Python：

- `download` / `clean`
- `features` / `rules:deviations` / `weather:router`
- `backtest:router` / `calibrate:router`
- `download:macro`
- `multi:1d` / `multi:weather` / `multi:summary` / `multi:periods`
- `/api/scanner/run?mode=summary`
- `/api/scanner/run?mode=full`

以下 Node scripts 不是当前 Python official 主路径。

## Explicit Legacy Fallbacks

这些命令是迁移期间的回退或对照入口。不要在新文档或自动化中把它们当默认路径。

| Script | Node target | Status |
| --- | --- | --- |
| `legacy:download` | `scripts/download-data.mjs` | Keep as rollback until Python data path has run in normal use. |
| `legacy:clean` | `scripts/clean-data.mjs` | Keep as rollback until Python clean path has run in normal use. |
| `legacy:features` | `scripts/build-feature-factory.mjs` | Keep as parity rollback. |
| `legacy:rules:deviations` | `scripts/build-deviation-rules.mjs` | Keep as parity rollback. |
| `legacy:weather:router` | `scripts/build-market-weather-router.mjs` | Keep as parity rollback. |
| `legacy:backtest:router` | `scripts/backtest-strategy-router.mjs` | Keep as router research rollback. |
| `legacy:calibrate:router` | `scripts/calibrate-router.mjs` | Keep as router research rollback. |
| `legacy:download:macro` | `scripts/download-macro-data.mjs` | Keep as macro data rollback. |
| `legacy:multi:1d` | `scripts/run-multi-symbol-1d.mjs` | Keep as historical scanner rollback. |
| `legacy:multi:weather` | `scripts/run-multi-symbol-1d.mjs` | Keep as historical scanner rollback. |
| `legacy:multi:periods` | `scripts/run-multi-symbol-1d.mjs` | Keep as historical scanner rollback. |

Removal condition: remove only after at least one normal Python official data/report refresh cycle has passed and rollback is no longer needed.

## Retained Runtime Utility

| Script | Node target | Recommendation |
| --- | --- | --- |
| `serve` | `server.mjs` | Low priority. It only serves static frontend files. Replace with FastAPI static files only if we want a single-process dev server. |

## Research And Training Commands Still In Node

These are not part of the official report writer path, but they still matter for research continuity.

| Script | Node target | Category | Recommendation |
| --- | --- | --- | --- |
| `backtest:indicators` | `scripts/backtest-indicators.mjs` | Historical research | Keep temporarily; migrate only if the indicator backtest becomes an active workflow. |
| `backtest:volatility` | `scripts/backtest-volatility-state.mjs` | Historical research | Keep temporarily; likely replace with Python notebooks/CLI if reused. |
| `backtest:position` | `scripts/backtest-position-state.mjs` | Historical research | Keep temporarily; Python deviation rules already cover the production-facing output. |
| `backtest:deviations` | `scripts/backtest-deviations.mjs` | Historical research | Keep temporarily; production deviation rules are already Python. |
| `compare:macro` | `scripts/compare-macro-impact.mjs` | Macro research | Migrate together with the Python decision-tree validation stack. |
| `train:state` | `scripts/train-market-state.mjs` | Model training | Keep until ML training direction is decided. |
| `train:trees` | `scripts/train-decision-trees.mjs` | Model training | Keep until Python training stack is planned. |
| `validate:trees` | `scripts/validate-decision-trees.mjs` | Model validation | Keep until Python training stack is planned. |
| `journal:create` | `scripts/create-decision-journal.mjs` | Workflow utility | Low priority; migrate only if decision journal stays in product scope. |

## Suggested Migration Order

1. `train:state`, `train:trees`, `validate:trees`, and `compare:macro`: migrate as a Python ML/training milestone.
2. Historical `backtest:*` utilities and `journal:create`: migrate only if actively used.
3. `serve`: optional final cleanup.

## Verification

`backend_py.smoke_test` intentionally asserts the exact remaining Node script set. If a package script starts with `node`, update this inventory and the smoke test together.
