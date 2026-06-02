# Python Research Migration Spec

> Goal: move research logic into the Python ecosystem without replacing the current Node production path too early.

## Phase 1 Scope

This phase implements Python parity layers for the research outputs that can be
matched safely against current Node golden reports.

- Keep Node scripts as the production generator.
- Add Python modules under `backend_py/research/`.
- Generate Python comparison artifacts with `_py` suffix.
- Compare Python output against the Node report, ignoring only runtime timestamps
  and explicitly documented out-of-scope sections.
- Keep FastAPI/scanner Python paths explicit until parity coverage is broad
  enough to switch defaults.
- OKX download and clean aggregation now have Python equivalents, but Node
  remains the default production path until the full orchestrator is migrated.

## Files

Python implementation:

- `backend_py/research/config.py`
  - Mirrors `backtest/config.mjs` naming and stem rules.
- `backend_py/research/feature_factory.py`
  - Ports indicators and state feature dataset generation.
  - Ports weather labels and strategy routing.
  - Produces `featureStats`, `current.values`, `current.labels`, and strategy route fields.
- `backend_py/build_feature_factory.py`
  - CLI that reads `data/clean/*_clean.json`.
  - Writes `reports/*_feature_factory_py.json`.
  - Writes `reports/*_feature_factory_rows_py.csv`.
- `backend_py/compare_feature_factory.py`
  - Compares Node and Python reports.
  - Ignores `generatedAt`.
  - Recursively compares metadata, feature definitions, `featureStats`, and full `current`.
- `backend_py/research/summary.py`
  - Ports `historyQuality`, `qualitySummary`, and `buildSummaryRow`.
- `backend_py/build_summary.py`
  - Rebuilds from existing reports and clean payloads.
  - Writes `_py` suffixed multi-period summary artifacts.
- `backend_py/compare_summary.py`
  - Compares Node and Python summary JSON.
  - Ignores `startedAt` and `finishedAt`.
- `backend_py/research/market_weather_router.py`
  - Ports market weather router component classification, strategy router
    calibration, gate selection, and current snapshot row.
  - Reuses Python feature snapshots, weather labels, strategy routing, and
    deviation rules.
  - Produces `current`, `strategyScores`, `deviationFinalWeather`,
    `currentComponentRows`, and `componentSummaryRows`.
- `backend_py/build_market_weather_router.py`
  - CLI that reads `data/clean/*_clean.json`.
  - Writes `_market_weather_router_py.json` and `_py` component/score CSV files.
- `backend_py/compare_market_weather_router.py`
  - Compares Python router output against Node router reports.
  - Ignores `generatedAt`.
  - Compares calibration signals and gate selection.
- `backend_py/research/deviation_rules.py`
  - Ports deviation study state/metric aggregation and rule mapping.
  - Produces `finalWeather`, `currentRuleRows`, and `ruleLibraryRows`.
- `backend_py/build_deviation_rules.py`
  - CLI that reads `data/clean/*_clean.json`.
  - Writes `_deviation_rules_py.json` and `_py` rule CSV files.
- `backend_py/compare_deviation_rules.py`
  - Compares Python deviation rules against current Node deviation rule reports.
  - Ignores runtime timestamps and tolerates known optional fields from older
    generated reports.
- `backend_py/research/okx.py`
  - Ports OKX history-candles pagination, dynamic page budgeting, retry policy,
    truncation metadata, and raw payload shape.
- `backend_py/research/clean.py`
  - Ports OKX raw candle normalization, structural validation, extreme candle
    flagging, duplicate handling, missing-bar detection, and clean payload shape.
- `backend_py/download_data.py` / `backend_py/clean_data.py`
  - Python equivalents for the standalone Node download/clean CLIs.
- `backend_py/compare_clean_data.py`
  - Rebuilds Python clean payload from existing raw JSON and compares it against
    the existing Node clean JSON, ignoring only `metadata.cleanedAt`.
- `backend_py/run_data_pipeline.py`
  - Batch Python download + clean entry point used by scanner mode `python_data`.
- `backend_py/run_full_pipeline.py`
  - Python full orchestrator for download, clean, feature, deviation, router,
    and summary generation.
  - Writes `_py_full` report artifacts by default so it can be validated without
    replacing Node production reports.
  - Supports `--check-inputs` for raw/clean coverage inspection before large
    runs.
  - Supports `--official` for the later cutover step when Python becomes the
    production report writer.

## Feature Factory Parity Contract

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
- `current.weatherName`
- `current.weatherConfidencePct`
- `current.labels`
- `current.strategyScores`
- `current.topRoutes`
- `current.strategyRoutes`
- `current.values`

The Python report may differ for now:

- `metadata.generatedAt`

`generatedAt` is intentionally ignored because Node and Python are run at different times.

## Market Weather Router Parity Contract

The Python market weather router report must match Node for:

- `metadata.instrument`
- `metadata.bar`
- `metadata.fromDate`
- `metadata.toDate`
- `metadata.firstDate`
- `metadata.lastDate`
- `metadata.snapshotCount`
- `metadata.observationRows`
- `metadata.routerCalibrationRows`
- `metadata.routerCalibrationObservationRows`
- `metadata.gateSource`
- `metadata.calibrationConfidenceGate`
- `metadata.currentCalibrationSignals`
- `metadata.horizons`
- `metadata.routerPrinciple`
- `current`
- `strategyScores`
- `deviationFinalWeather`
- `currentComponentRows`
- `componentSummaryRows`

The Python router report may differ for now:

- `metadata.generatedAt`

`generatedAt` is intentionally ignored because Node and Python are run at
different times.

## Deviation Rules Parity Contract

The Python deviation rule report must match Node for:

- `metadata.instrument`
- `metadata.bar`
- `metadata.fromDate`
- `metadata.toDate`
- `metadata.firstDate`
- `metadata.lastDate`
- `metadata.snapshotCount`
- `metadata.stateObservationRows`
- `metadata.metricObservationRows`
- `metadata.horizons`
- `metadata.bucketScheme`
- `metadata.rulePrinciple`
- `finalWeather`
- `currentRuleRows`
- `ruleLibraryRows`

The Python deviation rule report may differ for now:

- `metadata.generatedAt`
- optional legacy-report fields such as `metadata.metricBucketMode` or
  `finalWeather.confidenceLimited` when an existing Node report was generated
  before those fields were added.

For strict parity, refresh the Node golden report with the current Node script
before running the Python comparison.

## Commands

Refresh the Node golden report from current clean candles:

```bash
npm run features -- --instrument BTC-USDT --bar 1D --days 3650
```

Generate Python parity output:

```bash
uv run python -m backend_py.build_feature_factory --instrument BTC-USDT --bar 1D --days 3650
```

Compare full JSON schema:

```bash
uv run python -m backend_py.compare_feature_factory --instrument BTC-USDT --bar 1D --days 3650
```

Generate and compare router parity output:

```bash
uv run python -m backend_py.build_market_weather_router --instrument BTC-USDT --bar 1D --days 3650
uv run python -m backend_py.compare_market_weather_router --instrument BTC-USDT --bar 1D --days 3650
```

Generate and compare deviation rule parity output:

```bash
node scripts/build-deviation-rules.mjs --instrument BTC-USDT --bar 1D --days 3650
uv run python -m backend_py.build_deviation_rules --instrument BTC-USDT --bar 1D --days 3650
uv run python -m backend_py.compare_deviation_rules --instrument BTC-USDT --bar 1D --days 3650
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

- Add a scanner mode for Python deviation parity across selected symbols/bars.
- Continue filling missing default-symbol raw inputs in batches with
  `run_data_pipeline --missing-only`; after the sixth batch, local coverage is
  96/174 required `1D,4H,8H` combinations.
- Expand `python_full` validation from `BTC/ETH × 1D/4H/8H` to the full default
  symbol set and bars after input coverage is available.
- Add an explicit cutover checklist for running `python_full --official` as the
  default production report writer.
- Start replacing selected Node scanner/orchestrator paths only after full-scope
  Python output has been reviewed.
