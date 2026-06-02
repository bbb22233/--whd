# Python Research Migration Spec

> Goal: move research logic into the Python ecosystem without replacing the current Node production path too early.

## Phase 1 Scope

This phase implements a Python parity layer for Feature Factory core values.

- Keep Node scripts as the production generator.
- Add Python modules under `backend_py/research/`.
- Generate Python comparison artifacts with `_py` suffix.
- Compare Python output against the Node report for stable numeric fields.
- Do not change FastAPI routes in this phase.
- Do not migrate OKX download, clean aggregation, market weather router, or deviation rules yet.

## Files

Python implementation:

- `backend_py/research/config.py`
  - Mirrors `backtest/config.mjs` naming and stem rules.
- `backend_py/research/feature_factory.py`
  - Ports indicators and state feature dataset generation.
  - Produces core `featureStats` and `current.values`.
  - Does not yet port weather labels or strategy routes.
- `backend_py/build_feature_factory.py`
  - CLI that reads `data/clean/*_clean.json`.
  - Writes `reports/*_feature_factory_py.json`.
  - Writes `reports/*_feature_factory_rows_py.csv`.
- `backend_py/compare_feature_factory.py`
  - Compares Node and Python reports.
  - Ignores `generatedAt`.
  - Compares metadata, feature definitions, `featureStats`, and `current.values`.

## Current Parity Contract

The Python report must match Node for:

- `metadata.instrument`
- `metadata.bar`
- `metadata.fromDate`
- `metadata.toDate`
- `metadata.firstDate`
- `metadata.lastDate`
- `metadata.snapshotCount`
- `metadata.featureCount`
- `features`
- `featureStats`
- `current.date`
- `current.close`
- `current.values`

The Python report may differ for now:

- `metadata.generatedAt`
- `metadata.pythonParityScope`
- `current.weatherName`
- `current.weatherConfidencePct`
- `current.labels`
- `current.strategyScores`
- `current.topRoutes`
- `current.strategyRoutes`

Those excluded fields still belong to Node until the next migration phase ports weather labels and strategy routing.

## Commands

Refresh the Node golden report from current clean candles:

```bash
npm run features -- --instrument BTC-USDT --bar 1D --days 3650
```

Generate Python parity output:

```bash
uv run python -m backend_py.build_feature_factory --instrument BTC-USDT --bar 1D --days 3650
```

Compare core fields:

```bash
uv run python -m backend_py.compare_feature_factory --instrument BTC-USDT --bar 1D --days 3650
```

Full validation:

```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py
uv run python -m backend_py.smoke_test
node --check app.js
node --check server.mjs
```

## Next Phase

The next Python research migration should choose one of:

- Port `buildWeatherLabels` and `routeStrategies` to make Feature Factory JSON complete.
- Port from-reports multi-period summary, which is lower algorithmic risk and mainly depends on report contracts.

