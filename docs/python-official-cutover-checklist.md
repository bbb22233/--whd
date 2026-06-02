# Python Official Report Cutover Checklist

本清单用于把 Python full pipeline 从 `_py_full` 对照报告切到正式 report writer。

## Preconditions

- Git worktree clean。
- 本地 default raw/clean input coverage 为 `174/174`。
- `python_full --skip-download --bars 1D,4H,8H --days 3650` 已通过完整 default symbols 验证。
- 运行前确认不会同时执行 Node `full` 或其他 report writer。

## Preflight Commands

```bash
git status --short --branch
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --plan-outputs --official --skip-download --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --bars 1D,4H,8H --days 3650
```

For compact output-plan review:

```bash
uv run python -m backend_py.run_full_pipeline --plan-outputs --official --skip-download --bars 1D,4H,8H --days 3650 \
  | python3 -c 'import json,sys; p=json.load(sys.stdin); print({k:p[k] for k in ["pathCount","existingCount","missingCount","official","suffix"]})'
```

Expected default official output plan:

```text
pathCount = 1748
official = true
suffix = ""
```

## Cutover Command

Only run this after the preflight is clean:

```bash
uv run python -m backend_py.run_full_pipeline --skip-download --official --bars 1D,4H,8H --days 3650
```

Expected:

```text
successCount = 174
weatherCount = 174
insufficientHistoryCount = 0
errorCount = 0
```

## Post-Cutover Checks

```bash
git diff --stat -- reports
uv run python -m backend_py.smoke_test
node --check app.js
node --check server.mjs
```

Also inspect the official combined report metadata:

```bash
python3 -c 'import json; p=json.load(open("reports/multi_period_market_weather_current.json")); print(p["metadata"])'
```

## Rollback

If official output is wrong before commit:

```bash
git restore reports
```

If the cutover commit has already been pushed, revert that commit instead of force-pushing.

## Scanner Entry Cutover

After official reports are reviewed and committed:

- `/api/scanner/run?mode=summary` should call `backend_py.run_full_pipeline --from-reports --summary-only --skip-download --official --days 3650 --bars 1D,4H,8H`.
- `/api/scanner/run?mode=full` should call `backend_py.run_full_pipeline --skip-download --official --days 3650 --bars 1D,4H,8H`.
- `/api/scanner/run?mode=node_summary` should remain as the legacy Node summary fallback until the rollback window closes.
- `/api/scanner/run?mode=node_full` should remain as the legacy Node fallback until the rollback window closes.
- `uv run python -m backend_py.smoke_test` must assert all four mappings.
