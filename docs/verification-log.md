# 验证日志 (Verification Log)

> Quant Monitor Terminal — 修复项的运行时验证记录。
> 配合 `docs/fix-spec.md`(在审查分支 `claude/crypto-monitor-audit-y9Qpq`)使用。

## 关于本文件

- **目的**:把"本地跑过、但没沉淀进仓库"的验证证据固化下来,做成可追溯记录。
- **填写方式**:每项按 **命令 → 期望 → 实际 → 备注** 四栏。`实际` 一栏先留 `TODO`,由本地 Codex/执行者跑完后填真实数字。
- **环境说明**:Claude 云端审查环境**无法访问 `www.okx.com`**(出网白名单 `Host not in allowlist`),且 `data/` 已移出 Git 跟踪,故云端无法复现下载/跑批。以下"实际值"必须在**能联网的本地环境**采集。
- **代码基线**:`main @ 2b0aac5`(含 Step 1–7 全部修复)。相关提交:
  - `aa0b244` fix(H4,L3) · `d06c360` fix(M1) · `053bc25` fix(L1,L2) · `585fb46` fix(L4)
  - `e3fce69` fix(H5) · `e6ad046` fix(M6) · `081d194` fix(L6) · `949fa95` fix(H2) · `2b0aac5` fix(H3)

填写约定:
- 实际值贴原始数字/片段;长输出可贴关键行 + `jq` 过滤结果。
- 每项填完把状态从 `⏳ 待填` 改为 `✅ 通过` 或 `❌ 不符`(不符时在备注写差异)。

---

## 1. H4 — 4H 下载不再被 8000 根截断

**状态:⏳ 待填**

### 命令
```bash
npm run download -- --instrument BTC-USDT --bar 4H --days 3650
# 读取产物关键字段(不改 download 脚本日志,直接看 raw JSON):
node -e 'const p=require("./data/raw/BTC_USDT_4H_raw.json");console.log(JSON.stringify({rowCount:p.rowCount,pageCount:p.pageCount,maxPages:p.maxPages,first:p.rows[0]?.[0],firstDate:new Date(Number(p.rows[0]?.[0])).toISOString(),truncated:p.truncated,oldestReachedDate:p.oldestReachedDate,retryCount:p.retryCount},null,2))'
```

### 期望
- `rowCount` **远超 8000**(旧版固定卡在 7999)。若 OKX 实际保有约 10 年 4H,应接近 ~21900;若 OKX 自身历史不足 10 年,`rowCount` 仍应明显 > 8000、`firstDate` 明显早于 `2022-10`。
- `maxPages` ≈ **266**(旧版硬编码 80)。
- 新增字段存在:`requestedStartMs / oldestReached / oldestReachedDate / truncated / retryCount / maxPages`。
- `truncated`:
  - 若回溯到了请求起点(10 年前) → `false`;
  - 若 OKX 自身没有 10 年 4H → `true`,但这是数据源限制,不是分页 bug(看 `oldestReachedDate` 是否等于 OKX 最早可得日期)。

### 实际
```
TODO: 贴上面 node 命令的 JSON 输出
rowCount   = TODO   (基线对照:旧版 7999)
maxPages   = TODO   (基线对照:旧版 80)
firstDate  = TODO   (基线对照:旧版 2022-10-05)
truncated  = TODO
```

### 备注
- **基线(bug 现场)**:`commit 91eb0bb` 下 `data/clean/BTC_USDT_4H_clean.json` 为 `rows=7999, first=2022-10-05`,正是 80 页 × 100 的上限截断。
- 判定通过标准:`rowCount ≫ 8000` 且 `firstDate` 明显前移;`truncated` 字段存在且取值与 `oldestReachedDate` 自洽。

---

## 2. BTC 4H — 主灯号由校准器驱动

**状态:⏳ 待填**

### 命令
```bash
# 前置:已 download + clean BTC-USDT 4H(或先跑过 multi)
npm run weather:router -- --instrument BTC-USDT --bar 4H --days 3650
jq '{gate:.current.gate, gateSource:.metadata.gateSource, top:.current.topWeatherRoute, topScore:.current.topWeatherScore, scores:[.strategyScores[]|{key,score}]}' reports/BTC_USDT_4H_market_weather_router.json
```

### 期望
- `current.gate` 为红/黄/绿系之一(`绿 / 黄偏绿 / 黄 / 黄偏红 / 红`)。
- `metadata.gateSource == "router_calibration"`(证明走的是校准器而非旧魔数 `score_fallback`)。
- `strategyScores` 为 5 项,key 为 **`trendFollowing / breakout / meanReversion / grid / wait`**(确认 L6 统一后命名,`trend` 已并为 `trendFollowing`)。
- 不再出现旧 `scoreStrategies` 的痕迹(全仓库 `grep -rn "scoreStrategies\|scoreStrategyFit" backtest/` 应为空)。

### 实际
```
gate       = TODO
gateSource = TODO   (期望 router_calibration)
scores keys= TODO   (期望 trendFollowing/breakout/meanReversion/grid/wait)
grep scoreStrategies/scoreStrategyFit = TODO (期望 空)
```

### 备注
- 若 `gateSource == "score_fallback"`,说明该品种当前没有校准信号(可能历史太短),需换样本充足的品种确认主路径。

---

## 3. 58 品种 4H 批量 — periodWeight 真正生效

**状态:⏳ 待填**

### 命令
```bash
node scripts/run-multi-symbol-1d.mjs --bars 4H
jq '{successCount:.metadata.successCount, weatherCount:.metadata.weatherCount, insufficient:.metadata.insufficientHistoryCount, errorCount:.metadata.errorCount, weightedWeatherCount:.metadata.weightedWeatherCount, averagePeriodWeight:.metadata.averagePeriodWeight, lowWeightCount:.metadata.lowWeightCount}' reports/multi_4H_market_weather_current.json
# 抽查薄历史品种的权重分布:
jq -r '.rows[] | [.instrument, .dataStatus, .historyQuality, .periodWeight] | @tsv' reports/multi_4H_market_weather_current.json | sort -k4 -n | head -15
```

### 期望
- 产出 `reports/multi_4H_market_weather_current.{json,csv}`。
- `successCount` 接近 58(扣除 OKX 无足够历史/下载失败的品种)。
- metadata 含 H5 的**聚合消费**字段:`weightedWeatherCount / averagePeriodWeight / lowWeightCount`(不再只是每行罗列 `periodWeight`)。
- 薄历史/被截断品种 `periodWeight < 1`(`historyQuality` 为 `half_weight` 或 `weak_display_only`);BTC 等厚历史 `periodWeight == 1`。

### 实际
```
successCount         = TODO
errorCount           = TODO
weightedWeatherCount = TODO
averagePeriodWeight  = TODO
lowWeightCount       = TODO
低权重品种样例        = TODO (贴 sort 后前几行)
```

### 备注
- `errorCount` 偏高时,贴 `.errors` 看是否为 OKX 历史不足(可接受)还是下载/解析异常(需查)。

---

## 4. Step 7b — router calibration 接入证据

**状态:⏳ 待填**

### 命令
```bash
jq '{gateSource:.metadata.gateSource, calibrationRows:.metadata.routerCalibrationRows, calibrationObsRows:.metadata.routerCalibrationObservationRows, signals:[.metadata.currentCalibrationSignals[]|{routeKey,light,currentScore,calibrationScore,sampleConfidencePct,bestHorizon}]}' reports/BTC_USDT_4H_market_weather_router.json
```

### 期望
- `metadata.gateSource == "router_calibration"`。
- `metadata.routerCalibrationRows > 0`、`routerCalibrationObservationRows > 0`。
- `metadata.currentCalibrationSignals` 非空,每条含 `routeKey / light / calibrationScore / sampleConfidencePct / bestHorizon`。
- `current.topWeatherRoute` 与得分最高(且通过样本闸)的校准信号一致。

### 实际
```
gateSource         = TODO
routerCalibrationRows = TODO
signals(条数/示例) = TODO
```

### 备注
- 这是"校准器已真正接入主灯号"的直接证据(对应 H2)。旧版本该字段不存在、gateSource 概念也没有。

---

## 5. Step 7c — 小样本绿灯被降级 + 偏离规则置信门

**状态:⏳ 待填**

### 命令
```bash
# (a) 折叠层样本闸:找出 rawLight=绿灯 但被降级为 light=黄灯 的信号
#     BTC 4H 样本通常充足、不一定触发;优先用薄历史品种或 1W 周期
jq '[.metadata.currentCalibrationSignals[] | select(.confidenceGate=="样本不足")] | {downgraded:[.[]|{routeKey,rawLight,light,occurrences,sampleConfidencePct,confidenceGateReason}]}' reports/<薄样本品种>_4H_market_weather_router.json

# (b) 偏离规则置信门:finalWeather 因样本偏少把"黄偏绿"降为"黄灯"
jq '.deviationFinalWeather | {gate, confidenceLimited, ruleConfidence, actionBias}' reports/<薄样本品种>_4H_market_weather_router.json
```

### 期望
- (a) 至少能找到一条 `confidenceGate=="样本不足"` 的信号,且其 `rawLight=="绿灯"` 而 `light=="黄灯"`,`confidenceGateReason` 说明 `occurrences < 30` 或 `sampleConfidencePct < 40`。
- (b) 能找到一例 `confidenceLimited == true`,且当原始偏离 gate 为"黄偏绿"时被降级为"黄灯",`actionBias` 含"样本偏少…不升级主灯号"。
- 阈值与代码一致:`MIN_CALIBRATION_OCCURRENCES = 30`、`MIN_CALIBRATION_CONFIDENCE_PCT = 40`。

### 实际
```
(a) 降级信号样例 = TODO (期望 rawLight=绿灯 → light=黄灯)
(b) confidenceLimited 触发样例 = TODO
```

### 备注
- 厚样本品种(如 BTC 4H)可能**不触发**降级,这本身正常;需主动挑一个**小样本**品种/周期(新上市币、或 `--bars 1W` 的短历史)来证明降级逻辑生效。
- 若全样本都不触发,可临时用一个上市时间很短的品种做对照。

---

## 附:回归健全性(可选)

**状态:⏳ 待填**

确认修复未破坏既有产物结构 / 前端可渲染:
```bash
npm run serve   # 浏览器开 ?symbol=BTC-USDT&bar=4H,确认页面正常渲染、无 console 报错
grep -rn "scoreStrategies\|scoreStrategyFit" backtest/   # 期望:空(死代码与旧打分已删)
```

实际:`TODO`

---

## 6. Step 9 — 前端健壮性(M4/M5)

**状态:✅ 通过**

### 命令
```bash
node --check app.js
rg -n '"kindKey": "ma233"|kindKey.*ma233' reports/BTC_USDT_1D_deviation_rules.json reports/BTC_USDT_4H_deviation_rules.json app.js
curl -I http://127.0.0.1:4177/
```

### 期望
- `app.js` 语法检查通过。
- `renderComponentGrid` 使用 `kindKey === "ma233"` 匹配 233MA 乖离规则。
- BTC 1D/4H deviation rules 中存在 `kindKey:"ma233"`。
- 本地前端入口返回 HTTP 200。
- `weather.current` 为空时进入样本不足占位,不再抛 `weather.current.date` 的 TypeError。

### 实际
```
node --check app.js = 通过
app.js maRule kindKey = ma233
reports/BTC_USDT_1D_deviation_rules.json = 存在 ma233
reports/BTC_USDT_4H_deviation_rules.json = 存在 ma233
http://127.0.0.1:4177/ = 200 OK
```

### 备注
- 已新增 `renderInsufficient` 守卫: `if (!weather?.current) { renderInsufficient(weather?.metadata); return; }`。
- Codex 浏览器插件初始化失败(`failed to write kernel assets`),本轮未完成可视化浏览器截图验证;需在浏览器插件可用时补一次无 console 错误的可视复验。

---

## 7. Python API — 前端数据源迁移第一步

**状态:✅ 通过**

### 命令
```bash
uv run python -m backend_py.smoke_test
node --check app.js
# 临时启动 FastAPI 后:
curl -fsS http://127.0.0.1:8000/api/reports/BTC_USDT_1D_market_weather_router.json
# 需要本地已生成 data/clean;干净 clone 可先跳过,或预期返回 404:
curl -fsS http://127.0.0.1:8000/api/candles/BTC-USDT/1D
```

### 期望
- Python 后端可读取 legacy report JSON 与 clean candles。
- 前端 `PATHS` 优先指向 `http://127.0.0.1:8000/api/...`。
- Python API 不可用时,前端仍可 fallback 到原静态文件路径。
- `data/clean/` 不进 Git;干净 clone 中 clean candles 端点可返回明确 404,跑过 download/clean 后应返回 200。

### 实际
```
uv run python -m backend_py.smoke_test = 通过
node --check app.js = 通过
/api/reports/BTC_USDT_1D_market_weather_router.json = 200 OK, instrument BTC-USDT, bar 1D
/api/candles/BTC-USDT/1D = clean data 存在时 200 OK;干净 clone 中 404 Clean candles not found
```

### 备注
- 这是迁移桥接层:前端数据入口先切到 Python API,但 Node 仍负责生成 reports/data。
- 仍保留静态 fallback,避免 Python 后端未启动时页面直接不可用。
- `backend_py.smoke_test` 已对缺失的未跟踪 clean data 做降级标记:`cleanCandlesStatus=missing_untracked_data`。

---

## 8. Python API — Dashboard 聚合端点迁移

**状态:✅ 通过**

### 命令
```bash
uv run python -m backend_py.smoke_test
uv run python -m py_compile backend_py/*.py
node --check app.js
node --check server.mjs
uv run uvicorn backend_py.main:app --host 127.0.0.1 --port 8000
curl -fsS "http://127.0.0.1:8000/api/dashboard/current?instrument=BTC-USDT&bar=1D"
curl -i "http://127.0.0.1:8000/api/dashboard/current?instrument=BTC-USDT&bar=BAD"
curl -i "http://127.0.0.1:8000/api/dashboard/current?instrument=NO-SUCH&bar=1D"
node server.mjs
curl -I http://127.0.0.1:4177/
```

### 期望
- 前端主路径读取 `GET /api/dashboard/current?instrument=BTC-USDT&bar=1D`。
- Dashboard API 一次返回 `weather/features/deviations/candles`。
- `weather` 和 `features` 为必需源,缺失时返回 404。
- `deviations` 和 `candles` 为可选源,缺失时返回 200 且字段为 `null`。
- 非法 dashboard 周期返回 400。
- Python API 不可用时,前端仍回退到旧的 reports/data 静态路径。

### 实际
```
uv run python -m backend_py.smoke_test = 通过, dashboardCandlesStatus=ok
uv run python -m py_compile backend_py/*.py = 通过
node --check app.js = 通过
node --check server.mjs = 通过
/api/dashboard/current?instrument=BTC-USDT&bar=1D = 200 OK
Dashboard sources = weather ok, features ok, deviations ok, candles ok
/api/dashboard/current?instrument=BTC-USDT&bar=BAD = 400 Unsupported bar: BAD
/api/dashboard/current?instrument=NO-SUCH&bar=1D = 404 Report not found
ReportsReader 使用空 clean_dir 时 = candlesStatus missing_optional, candles null
http://127.0.0.1:4177/ = 200 OK
```

### 备注
- 已新增 `docs/api-dashboard-spec.md` 作为代理执行规格。
- 前端保留 `fetchLegacyDashboardData`,但 clean candles 降级为 optional,干净 clone 不再因为 `./data/clean/*_clean.json` 缺失而加载失败。
- 本轮 `tool_search` 未暴露可用的浏览器控制工具,因此没有补可视化截图;已用本地 HTTP 和静态检查完成可运行验证。

---

## 9. Node -> Python 研究迁移第一步

**状态:✅ 通过**

### 命令
```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py
uv run python -m backend_py.smoke_test
node --check app.js
node --check server.mjs
for f in scripts/*.mjs; do node --check "$f" >/dev/null || exit 1; done
npm run features -- --instrument BTC-USDT --bar 1D --days 3650
uv run python -m backend_py.build_feature_factory --instrument BTC-USDT --bar 1D --days 3650
uv run python -m backend_py.compare_feature_factory --instrument BTC-USDT --bar 1D --days 3650
```

### 期望
- Python 新增 feature factory core parity 层,不替换 Node 生产脚本。
- Python 从 `data/clean/BTC_USDT_1D_clean.json` 生成 `_feature_factory_py.json`。
- Python 与 Node 当前 `reports/BTC_USDT_1D_feature_factory.json` 在核心数值字段一致。
- 忽略 `generatedAt`、weather labels、strategy routes,这些仍由 Node 负责。
- FastAPI dashboard/smoke test 不受影响。

### 实际
```
py_compile backend_py/*.py backend_py/research/*.py = 通过
backend_py.smoke_test = 通过
node --check app.js = 通过
node --check server.mjs = 通过
node --check scripts/*.mjs = 通过
npm run features BTC-USDT 1D = 通过,刷新 Node golden report 到 2026-05-31
build_feature_factory.py BTC-USDT 1D = 通过
compare_feature_factory.py BTC-USDT 1D = status ok
snapshotCount = 2924
featureCount = 47
currentDate = 2026-05-31
```

### 备注
- 已新增 `docs/python-research-migration-spec.md`。
- 本阶段 Python 只覆盖 indicators + state feature dataset + core current values。
- `_feature_factory_py.json` 与 rows CSV 是本地验证产物,已加入 `.gitignore`。
- 下一阶段可继续补齐 `buildWeatherLabels` / `routeStrategies`,或按代理建议迁移 from-reports multi-period summary。

---

## 10. Python Feature Factory 完整 Schema Parity

**状态:✅ 通过**

### 命令
```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py
uv run python -m backend_py.smoke_test
node --check app.js
node --check server.mjs
for f in scripts/*.mjs; do node --check "$f" >/dev/null || exit 1; done
npm run features -- --instrument BTC-USDT --bar 1D --days 3650
uv run python -m backend_py.build_feature_factory --instrument BTC-USDT --bar 1D --days 3650
uv run python -m backend_py.compare_feature_factory --instrument BTC-USDT --bar 1D --days 3650
```

### 期望
- Python feature factory 不再只比 core values,而是补齐 `weatherName`、`labels`、`strategyScores`、`topRoutes`、`strategyRoutes`。
- `compare_feature_factory.py` 递归比较 dict/list,保留 route 排序比较。
- 仅忽略 `metadata.generatedAt`。
- Node 仍是生产输出,Python 继续写 `_feature_factory_py.json` 作为对照产物。

### 实际
```
py_compile backend_py/*.py backend_py/research/*.py = 通过
backend_py.smoke_test = 通过
node --check app.js = 通过
node --check server.mjs = 通过
node --check scripts/*.mjs = 通过
npm run features BTC-USDT 1D = 通过
build_feature_factory.py BTC-USDT 1D = 通过
compare_feature_factory.py BTC-USDT 1D = status ok
snapshotCount = 2924
featureCount = 47
currentDate = 2026-05-31
```

### 备注
- 代理审查确认 `current` 完整字段顺序为 `date/close/weatherName/weatherConfidencePct/labels/strategyScores/topRoutes/strategyRoutes/values`。
- 已同步更新 `docs/python-research-migration-spec.md`。
- 计划中的 `ETH-USDT 4H` 抽样未执行:本地当前只有 `data/clean/BTC_USDT_1D_clean.json`,缺少 `ETH_USDT_4H_clean.json`。

---

## 11. Python From-Reports Summary Parity

**状态:✅ 通过**

### 命令
```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py
node --check scripts/run-multi-symbol-1d.mjs
npm run multi:periods -- --from-reports --summary-only --symbols BTC-USDT --bars 1D
uv run python -m backend_py.build_summary --from-reports --summary-only --symbols BTC-USDT --bars 1D
uv run python -m backend_py.compare_summary --from-reports --summary-only --symbols BTC-USDT --bars 1D
git restore reports/multi_1D_market_weather_current.csv reports/multi_1D_market_weather_current.json reports/multi_period_market_weather_current.csv reports/multi_period_market_weather_current.json
```

### 期望
- Python 从现有 `data/clean`、`reports/*_market_weather_router.json`、可选 feature/deviation reports 重建 summary。
- `buildSummaryRow`、`historyQuality`、`qualitySummary` 与 Node from-reports 路径一致。
- Python 只写 `_py` suffixed summary artifacts,不替换 Node 正式 summary。
- 对比忽略 `startedAt` / `finishedAt`。

### 实际
```
py_compile backend_py/*.py backend_py/research/*.py = 通过
node --check scripts/run-multi-symbol-1d.mjs = 通过
Node from-reports summary BTC-USDT 1D = 通过
Python build_summary BTC-USDT 1D = 通过
compare_summary BTC-USDT 1D = status ok
rowCount = 1
errorCount = 0
weightedWeatherCount = 0.7
```

### 备注
- 本地当前只有 `data/clean/BTC_USDT_1D_clean.json`,所以本轮显式限制 `--symbols BTC-USDT --bars 1D`。
- Node 对照命令会覆盖正式 `multi_*` summary;验证后已用 `git restore` 恢复,避免破坏当前多币种前端数据。
- `_py` summary JSON/CSV 已加入 `.gitignore`。

---

## 12. Scanner Python Summary Mode

**状态:✅ 通过**

### 命令
```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py
uv run python -m backend_py.smoke_test
node --check app.js
node --check server.mjs
uv run python - <<'PY'
import time
from backend_py.scanner_service import ScannerService
scanner = ScannerService()
job = scanner.start("python_summary")
last = None
for _ in range(100):
    snapshot = scanner.snapshot()
    last = snapshot["lastJob"]
    if last and last["status"] != "running":
        break
    time.sleep(0.1)
print({"startedMode": job["mode"], "status": last["status"], "returnCode": last["returnCode"]})
assert last["status"] == "succeeded", last
PY
```

### 期望
- `/api/scanner/run?mode=python_summary` 可触发 Python from-reports summary parity。
- 新模式只写 `_py` 对照产物,不替换正式 Node summary。
- `scanner/status` 的 `supportedModes` 包含 `python_summary`。
- 启动瞬间 `snapshot.active` 不因子线程 pid 尚未写入而闪烁为 false。

### 实际
```
py_compile backend_py/*.py backend_py/research/*.py = 通过
backend_py.smoke_test = 通过
node --check app.js = 通过
node --check server.mjs = 通过
ScannerService().start("python_summary") = succeeded, returnCode 0
```

### 备注
- `python_summary` 当前默认使用本地可验证样本: `BTC-USDT 1D`。
- 后续生成更多 `data/clean` 后,可把该模式扩展为全 symbols/bars 或增加参数化 scanner API。

---

## 13. Python Parity Sample Expansion

**状态:✅ 通过**

### 命令
```bash
npm run download -- --instrument BTC-USDT --bar 4H --days 3650
npm run clean -- --instrument BTC-USDT --bar 4H --days 3650
npm run download -- --instrument ETH-USDT --bar 1D --days 3650
npm run clean -- --instrument ETH-USDT --bar 1D --days 3650
npm run download -- --instrument ETH-USDT --bar 4H --days 3650
npm run clean -- --instrument ETH-USDT --bar 4H --days 3650

npm run features -- --instrument BTC-USDT --bar 4H --days 3650
uv run python -m backend_py.build_feature_factory --instrument BTC-USDT --bar 4H --days 3650
uv run python -m backend_py.compare_feature_factory --instrument BTC-USDT --bar 4H --days 3650

npm run features -- --instrument ETH-USDT --bar 1D --days 3650
uv run python -m backend_py.build_feature_factory --instrument ETH-USDT --bar 1D --days 3650
uv run python -m backend_py.compare_feature_factory --instrument ETH-USDT --bar 1D --days 3650

npm run features -- --instrument ETH-USDT --bar 4H --days 3650
uv run python -m backend_py.build_feature_factory --instrument ETH-USDT --bar 4H --days 3650
uv run python -m backend_py.compare_feature_factory --instrument ETH-USDT --bar 4H --days 3650

npm run weather:router -- --instrument BTC-USDT --bar 1D --days 3650
npm run weather:router -- --instrument BTC-USDT --bar 4H --days 3650
npm run weather:router -- --instrument ETH-USDT --bar 1D --days 3650
npm run weather:router -- --instrument ETH-USDT --bar 4H --days 3650
npm run multi:periods -- --from-reports --summary-only --symbols BTC-USDT ETH-USDT --bars 1D,4H
uv run python -m backend_py.build_summary --from-reports --summary-only --symbols BTC-USDT ETH-USDT --bars 1D,4H
uv run python -m backend_py.compare_summary --from-reports --summary-only --symbols BTC-USDT ETH-USDT --bars 1D,4H
```

### 期望
- Python feature factory parity 覆盖不再只依赖 `BTC-USDT 1D`。
- 新增 `BTC-USDT 4H`、`ETH-USDT 1D`、`ETH-USDT 4H` 三个 clean 样本。
- Python summary parity 覆盖 `BTC/ETH x 1D/4H` 四行。
- 大型 `*_market_weather_observations.csv` 明细副产物不进 Git。

### 实际
```
BTC-USDT 4H cleanRows = 18382
ETH-USDT 1D cleanRows = 3156
ETH-USDT 4H cleanRows = 18382

compare_feature_factory BTC-USDT 4H = status ok, snapshotCount 18150, currentDate 2026-06-01 20:00
compare_feature_factory ETH-USDT 1D = status ok, snapshotCount 2924, currentDate 2026-05-31
compare_feature_factory ETH-USDT 4H = status ok, snapshotCount 18150, currentDate 2026-06-01 20:00

compare_summary BTC/ETH 1D/4H = status ok
rowCount = 4
errorCount = 0
weightedWeatherCount = 2.8
```

### 备注
- `data/raw` 与 `data/clean` 仍按 `.gitignore` 保留为本地数据,不提交。
- Node 小样本 summary 会覆盖正式 `multi_*` summary;验证后已恢复正式 summary。
- Router 生成的 `*_market_weather_observations.csv` 明细文件体积较大,已删除本地副产物。

---

## 14. Parameterized Python Summary Scanner

**状态:✅ 通过**

### 命令
```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py
uv run python -m backend_py.smoke_test
node --check app.js
node --check server.mjs
for f in scripts/*.mjs; do node --check "$f" >/dev/null || exit 1; done
uv run python - <<'PY'
import time
from backend_py.scanner_service import ScannerService
scanner = ScannerService()
job = scanner.start("python_summary", symbols="BTC-USDT,ETH-USDT", bars="1D,4H")
last = None
for _ in range(100):
    snapshot = scanner.snapshot()
    last = snapshot["lastJob"]
    if last and last["status"] != "running":
        break
    time.sleep(0.1)
print({"startedMode": job["mode"], "status": last["status"], "returnCode": last["returnCode"]})
assert last["status"] == "succeeded", last
PY
```

### 期望
- `/api/scanner/run?mode=python_summary&symbols=BTC-USDT,ETH-USDT&bars=1D,4H` 可运行。
- `python_summary` 默认仍是 `BTC-USDT 1D`,但可通过 query 参数扩大范围。
- `summary` 模式也可接收 `symbols/bars` 作为 Node from-reports scope。
- `full` 模式暂不透传 scope,避免误触发大范围下载语义变化。

### 实际
```
py_compile backend_py/*.py backend_py/research/*.py = 通过
backend_py.smoke_test = 通过
node --check app.js = 通过
node --check server.mjs = 通过
node --check scripts/*.mjs = 通过
ScannerService().start("python_summary", symbols="BTC-USDT,ETH-USDT", bars="1D,4H") = succeeded, returnCode 0
```

### 备注
- 参数化 `python_summary` 仍只写 `_py` summary artifacts,不覆盖正式 Node summary。

---

## 15. Python Market Weather Router Full Parity

**状态:✅ 通过**

### 命令
```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py

for instrument in BTC-USDT ETH-USDT; do
  for bar in 1D 4H; do
    uv run python -m backend_py.build_market_weather_router --instrument "$instrument" --bar "$bar" --days 3650
    uv run python -m backend_py.compare_market_weather_router --instrument "$instrument" --bar "$bar" --days 3650
  done
done
```

### 期望
- Python 版完整 market weather router 与 Node golden reports 对齐。
- 对齐范围包括 `current`、`strategyScores`、`deviationFinalWeather`、`currentComponentRows`、`componentSummaryRows`。
- 对比 metadata 包括 `instrument/bar/fromDate/toDate/firstDate/lastDate/snapshotCount/observationRows/routerCalibrationRows/routerCalibrationObservationRows/gateSource/calibrationConfidenceGate/currentCalibrationSignals/horizons/routerPrinciple`。
- `_py` router JSON/CSV 只作为本地验证产物,不替换 Node 正式报告。
- Router calibration/gate selection 已纳入比较。

### 实际
```
py_compile backend_py/*.py backend_py/research/*.py = 通过

compare_market_weather_router BTC-USDT 1D = status ok
snapshotCount = 2924
gate = 黄
gateSource = router_calibration
strategyScoreCount = 5
currentComponentRowCount = 20
componentSummaryRowCount = 80

compare_market_weather_router BTC-USDT 4H = status ok
snapshotCount = 18150
gate = 黄偏绿
gateSource = router_calibration
strategyScoreCount = 5
currentComponentRowCount = 20
componentSummaryRowCount = 80

compare_market_weather_router ETH-USDT 1D = status ok
snapshotCount = 2924
gate = 绿
gateSource = router_calibration
strategyScoreCount = 5
currentComponentRowCount = 20
componentSummaryRowCount = 80

compare_market_weather_router ETH-USDT 4H = status ok
snapshotCount = 18150
gate = 黄偏红
gateSource = router_calibration
strategyScoreCount = 5
currentComponentRowCount = 20
componentSummaryRowCount = 80
```

### 备注
- Python 复用已对齐的 feature snapshots、weather labels、strategy routing、deviation rules,并补齐 strategy router backtest、router calibration、confidence gate、主灯号 gate selection 与 current snapshot row。
- Node 的中文 `localeCompare("zh-CN")` 排序在 Python 中用显式状态顺序表固定,避免不同运行环境排序差异。
- Comparer 数值容忍为 `1e-2`,用于吸收 JS `toFixed` 与 Python 浮点格式化边界差。
- 下一步可把 Python router parity 接入 scanner/orchestrator 的显式模式,仍不直接替换 Node 默认生产路径。

---

## 16. Python Deviation Rules Parity

**状态:✅ 通过**

### 命令
```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py

for instrument in BTC-USDT ETH-USDT; do
  for bar in 1D 4H; do
    node scripts/build-deviation-rules.mjs --instrument "$instrument" --bar "$bar" --days 3650
    uv run python -m backend_py.build_deviation_rules --instrument "$instrument" --bar "$bar" --days 3650
    uv run python -m backend_py.compare_deviation_rules --instrument "$instrument" --bar "$bar" --days 3650
  done
done
```

### 期望
- Python 版 deviation study + deviation rules 与当前 Node golden reports 对齐。
- 对齐范围包括 `finalWeather`、`currentRuleRows`、`ruleLibraryRows`。
- 对比 metadata 包括 `instrument/bar/fromDate/toDate/firstDate/lastDate/snapshotCount/stateObservationRows/metricObservationRows/horizons/bucketScheme/rulePrinciple`。
- `_py` deviation JSON/CSV 只作为本地验证产物,不替换 Node 正式报告。
- 先刷新 Node golden report,避免仓库中旧 report 的日期或可选字段造成误判。

### 实际
```
py_compile backend_py/*.py backend_py/research/*.py = 通过

compare_deviation_rules BTC-USDT 1D = status ok
snapshotCount = 2924
currentRuleRowCount = 8
ruleLibraryRowCount = 40
finalGate = 黄灯

compare_deviation_rules BTC-USDT 4H = status ok
snapshotCount = 18150
currentRuleRowCount = 8
ruleLibraryRowCount = 40
finalGate = 黄偏红

compare_deviation_rules ETH-USDT 1D = status ok
snapshotCount = 2924
currentRuleRowCount = 8
ruleLibraryRowCount = 40
finalGate = 黄灯

compare_deviation_rules ETH-USDT 4H = status ok
snapshotCount = 18150
currentRuleRowCount = 8
ruleLibraryRowCount = 40
finalGate = 黄偏红
```

### 备注
- Python 复用已对齐的 indicator snapshots,并补齐 deviation state/metric observations、summary、rule library 与 final weather。
- Comparer 数值容忍为 `1e-2`,用于吸收 JS `toFixed` 与 Python 浮点格式化在百分位中位数上的 0.01 边界差。
- 本轮验证临时刷新了四组正式 Node deviation reports;验证后已恢复,不提交 report churn。
- Router calibration/gate selection 已在第 15 步补齐;下一步可接入 scanner/orchestrator 的显式 Python router 模式。

---

## 17. Scanner Python Router Mode

**状态:✅ 通过**

### 命令
```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py
uv run python -m backend_py.run_router_parity
uv run python -m backend_py.run_router_parity --symbols BTC-USDT ETH-USDT --bars 1D,4H
uv run python -m backend_py.smoke_test
uv run python - <<'PY'
import time
from backend_py.scanner_service import ScannerService
scanner = ScannerService()
job = scanner.start("python_router")
last = None
for _ in range(120):
    snapshot = scanner.snapshot()
    last = snapshot["lastJob"]
    if last and last["status"] != "running":
        break
    time.sleep(0.1)
print({"startedMode": job["mode"], "status": last["status"], "returnCode": last["returnCode"]})
assert last["status"] == "succeeded", last
PY
```

### 期望
- `/api/scanner/run?mode=python_router` 可运行。
- `python_router` 默认跑 `BTC-USDT 1D`,只写 `_py` router artifacts,不替换 Node 正式报告。
- `python_router` 可通过 `symbols/bars` 参数扩大范围,例如 `symbols=BTC-USDT,ETH-USDT&bars=1D,4H`。
- `scanner/status` 的 `supportedModes` 包含 `python_router`。

### 实际
```
py_compile backend_py/*.py backend_py/research/*.py = 通过
backend_py.run_router_parity = status ok, BTC-USDT 1D, gate 黄, gateSource router_calibration
backend_py.run_router_parity --symbols BTC-USDT ETH-USDT --bars 1D,4H = successCount 4, errorCount 0
backend_py.smoke_test = 通过
ScannerService().start("python_router") = succeeded, returnCode 0
```

### 备注
- 新增 `backend_py.run_router_parity`,负责按 symbols/bars 批量执行 Python router build + compare。
- `python_router` 与 `python_summary` 一样是显式 parity 模式,不会改变 Node 默认生产扫描路径。

---

## 18. Scanner Python Research Mode

**状态:✅ 通过**

### 命令
```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py
uv run python -m backend_py.run_research_parity
uv run python -m backend_py.smoke_test
uv run python - <<'PY'
import time
from backend_py.scanner_service import ScannerService
scanner = ScannerService()
job = scanner.start("python_research")
last = None
for _ in range(180):
    snapshot = scanner.snapshot()
    last = snapshot["lastJob"]
    if last and last["status"] != "running":
        break
    time.sleep(0.1)
print({"startedMode": job["mode"], "status": last["status"], "returnCode": last["returnCode"]})
assert last["status"] == "succeeded", last
PY
```

### 期望
- `/api/scanner/run?mode=python_research` 可运行。
- `python_research` 默认跑 `BTC-USDT 1D`,串联 Python feature、deviation、router、summary build/compare。
- 所有产物只写 `_py` artifacts,不替换 Node 正式 reports。
- 当现有 Node golden 与当前局部 scope 不一致时,对应 compare 标记为 `skipped`,不刷新 Node 报告。

### 实际
```
py_compile backend_py/*.py backend_py/research/*.py = 通过
backend_py.run_research_parity = stepCount 8, successCount 6, skippedCount 2, errorCount 0
backend_py.smoke_test = 通过
ScannerService().start("python_research") = succeeded, returnCode 0
```

### 备注
- `deviation_compare` 跳过原因:仓库中 BTC-USDT 1D Node deviation golden 的 `lastDate` 为 `2026-05-29`,当前 router golden 的 `lastDate` 为 `2026-05-31`。
- `summary_compare` 跳过原因:仓库中 Node summary 是全量 58 symbols/4 bars,本次默认 Python research 只跑 `BTC-USDT 1D`。
- 新增 `backend_py.run_research_parity`,作为 Python 研究链路的一键 parity/orchestration 入口。

---

## 19. Python OKX Data Pipeline

**状态:✅ 通过**

### 命令
```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py

for instrument in BTC-USDT ETH-USDT; do
  for bar in 1D 4H; do
    uv run python -m backend_py.compare_clean_data --instrument "$instrument" --bar "$bar" --days 3650
  done
done

uv run python - <<'PY'
from backend_py.research.config import ResearchConfig
from backend_py.research.okx import download_okx_history
payload = download_okx_history(ResearchConfig(instrument="BTC-USDT", bar="1D", days=2, requestLimit=100))
print({"source": payload["source"], "instrument": payload["instrument"], "bar": payload["bar"], "rowCount": payload["rowCount"], "pageCount": payload["pageCount"], "truncated": payload["truncated"]})
assert payload["rowCount"] > 0
PY
```

### 期望
- Python OKX download 复刻 Node `downloadOkxHistory` 的分页、动态 `maxPages`、retry、truncation metadata 和 raw JSON shape。
- Python clean 复刻 Node `cleanOkxRaw` 的 candle normalization、结构校验、极端 K 线标记、重复处理和 missing bars 统计。
- Python clean 从现有 raw 重建出的 payload 与 Node clean payload 对齐,只忽略运行时间字段 `metadata.cleanedAt`。
- 新增 scanner mode `python_data`,但仍是显式模式,不会替换 Node 默认 `full` 生产路径。

### 实际
```
py_compile backend_py/*.py backend_py/research/*.py = 通过
compare_clean_data BTC-USDT 1D = status ok, cleanRows 3156, missingBars 0
compare_clean_data BTC-USDT 4H = status ok, cleanRows 18382, missingBars 0
compare_clean_data ETH-USDT 1D = status ok, cleanRows 3156, missingBars 0
compare_clean_data ETH-USDT 4H = status ok, cleanRows 18382, missingBars 0
download_okx_history BTC-USDT 1D days=2 = rowCount 2, pageCount 1, truncated false
```

### 备注
- 新增 `backend_py.research.okx`, `backend_py.research.clean`, `backend_py.download_data`, `backend_py.clean_data`, `backend_py.compare_clean_data`, `backend_py.run_data_pipeline`。
- `python_data` 会真实写入 `data/raw` 与 `data/clean`;它和只写 `_py` artifacts 的 parity 模式分开。

---

## 20. Python Full Orchestrator

**状态:✅ 通过**

### 命令
```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py
uv run python -m backend_py.run_full_pipeline --skip-download --symbols BTC-USDT --bars 1D --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --symbols BTC-USDT --bars 4H,8H --days 3650
uv run python - <<'PY'
import time
from backend_py.scanner_service import ScannerService
scanner = ScannerService()
job = scanner.start("python_full")
last = None
for _ in range(240):
    snapshot = scanner.snapshot()
    last = snapshot["lastJob"]
    if last and last["status"] != "running":
        break
    time.sleep(0.25)
print({"startedMode": job["mode"], "status": last["status"], "returnCode": last["returnCode"]})
assert last["status"] == "succeeded", last
PY
```

### 期望
- Python full orchestrator 串联 `download/clean -> feature -> deviation -> router -> summary`。
- 默认写 `_py_full` reports,不覆盖正式 Node reports。
- 支持 `--official` 作为后续切生产时的显式开关。
- 支持派生周期 `8H`:从 `4H` clean 聚合,不直接下载 8H。
- scanner/status 的 `supportedModes` 包含 `python_full`。

### 实际
```
py_compile backend_py/*.py backend_py/research/*.py = 通过
run_full_pipeline BTC-USDT 1D --skip-download = successCount 1, errorCount 0, suffix _py_full
run_full_pipeline BTC-USDT 4H,8H --skip-download = successCount 2, errorCount 0, suffix _py_full
ScannerService().start("python_full") = succeeded, returnCode 0
```

### 备注
- 新增 `backend_py.run_full_pipeline`,作为 Python 版完整扫描编排入口。
- 新增 `python_full` scanner mode。
- 本轮验证生成的 `reports/*_py_full.*` 是临时对照产物,已加入 `.gitignore`;正式切换前不提交。

---

## 21. Python Full Orchestrator Expanded Sample

**状态:✅ 通过**

### 命令
```bash
uv run python -m backend_py.run_full_pipeline --skip-download --symbols BTC-USDT ETH-USDT --bars 1D,4H,8H --days 3650
```

### 期望
- `python_full` 从 BTC 单样本扩大到 `BTC/ETH × 1D/4H/8H`。
- 1D/4H 读取本地 raw 并重新 clean。
- 8H 从 4H clean 聚合生成。
- 默认仍写 `_py_full` reports,不覆盖正式 Node reports。

### 实际
```
run_full_pipeline BTC-USDT ETH-USDT 1D,4H,8H --skip-download:
successCount = 6
weatherCount = 6
weightedWeatherCount = 4.2
averagePeriodWeight = 0.7
insufficientHistoryCount = 0
errorCount = 0

bar 1D: successCount 2, errorCount 0
bar 4H: successCount 2, errorCount 0
bar 8H: successCount 2, errorCount 0
```

### 备注
- 该验证覆盖了普通下载周期和派生周期。
- 下一步应扩大到默认 symbols 集合,建议先使用 `--skip-download` 验证本地已有 raw/clean 能覆盖多少,再决定是否让 `python_full` 负责联网补齐。

---

## 22. Python Full Input Coverage Check

**状态:✅ 通过**

### 命令
```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --check-inputs --symbols BTC-USDT ETH-USDT --bars 1D,4H,8H --days 3650
```

### 期望
- 全量跑 `python_full` 前可快速检查本地 `data/raw` 与 `data/clean` 覆盖情况。
- `--check-inputs` 不生成 reports,只输出 required/ready/missing 明细。
- 8H 的 raw requirement 指向 4H raw,符合派生周期设计。

### 实际
```
default symbols × 1D,4H,8H:
requiredCount = 174
rawReadyCount = 6
rawMissingCount = 168
cleanReadyCount = 6
cleanMissingCount = 168

BTC/ETH × 1D,4H,8H:
requiredCount = 6
rawReadyCount = 6
rawMissingCount = 0
cleanReadyCount = 6
cleanMissingCount = 0
```

### 备注
- 本地目前只有 BTC/ETH 的 1D/4H raw;BTC/ETH 的 8H 由 4H 派生,因此已覆盖 6 组。
- 默认 58 symbols 若要离线全量跑,还缺 56 个 symbols 的 1D raw 和 56 个 symbols 的 4H raw;8H 会复用 4H raw。

---

## 23. Python Data Pipeline Small Batch Fill

**状态:✅ 通过**

### 命令
```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py
uv run python -m backend_py.run_data_pipeline --missing-only --symbols BTC-USDT --bars 1D,4H --days 3650
uv run python -m backend_py.run_data_pipeline --missing-only --symbols SOL-USDT BNB-USDT XRP-USDT DOGE-USDT ADA-USDT --bars 1D,4H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --symbols SOL-USDT BNB-USDT XRP-USDT DOGE-USDT ADA-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
```

### 期望
- `run_data_pipeline` 支持 `--missing-only`,已有 raw 时跳过,缺失 raw 时下载并 clean。
- 第一批补齐 `SOL/BNB/XRP/DOGE/ADA × 1D/4H`。
- `python_full --skip-download` 可使用新 raw/clean 完整生成 1D/4H/8H 的 `_py_full` 对照 reports。
- 本地覆盖度从 6 组提升到 21 组。

### 实际
```
BTC-USDT 1D,4H --missing-only:
stepCount = 2
skippedCount = 2
errorCount = 0

SOL/BNB/XRP/DOGE/ADA × 1D/4H:
stepCount = 10
successCount = 10
errorCount = 0

rawRows / cleanRows:
SOL 1D = 2072 / 2071
BNB 1D = 1260 / 1259
XRP 1D = 3065 / 3064
DOGE 1D = 2515 / 2514
ADA 1D = 2872 / 2871
SOL 4H = 12428 / 12427
BNB 4H = 7558 / 7557
XRP 4H = 18386 / 18385
DOGE 4H = 15068 / 15067
ADA 4H = 17228 / 17227

python_full SOL/BNB/XRP/DOGE/ADA × 1D,4H,8H:
successCount = 15
weatherCount = 15
errorCount = 0

default symbols × 1D,4H,8H after fill:
requiredCount = 174
rawReadyCount = 21
rawMissingCount = 153
cleanReadyCount = 21
cleanMissingCount = 153
```

### 备注
- 新增 `run_data_pipeline --missing-only` 与 `--max-symbols`,用于可控分批补资料。
- `data/raw`、`data/clean` 和 `_py_full` reports 均不进入 Git。

---

## 24. Python Data Pipeline Small Batch Fill 2

**状态:✅ 通过**

### 命令
```bash
uv run python -m backend_py.run_full_pipeline --check-inputs --symbols LINK-USDT AVAX-USDT TON-USDT TRX-USDT DOT-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_data_pipeline --missing-only --symbols LINK-USDT AVAX-USDT TON-USDT TRX-USDT DOT-USDT --bars 1D,4H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --symbols LINK-USDT AVAX-USDT TON-USDT TRX-USDT DOT-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
```

### 期望
- 第二批补齐 `LINK/AVAX/TON/TRX/DOT × 1D/4H`。
- 补齐后 `python_full --skip-download` 可验证该批 1D/4H/8H 全链路。
- 本地覆盖度从 21 组提升到 36 组。

### 实际
```
LINK/AVAX/TON/TRX/DOT × 1D/4H:
stepCount = 10
successCount = 10
errorCount = 0

rawRows / cleanRows:
LINK 1D = 3065 / 3064
AVAX 1D = 2080 / 2079
TON 1D = 1496 / 1495
TRX 1D = 3065 / 3064
DOT 1D = 2111 / 2110
LINK 4H = 18386 / 18385
AVAX 4H = 12476 / 12475
TON 4H = 8973 / 8972
TRX 4H = 18386 / 18385
DOT 4H = 12662 / 12661

python_full LINK/AVAX/TON/TRX/DOT × 1D,4H,8H:
successCount = 15
weatherCount = 15
errorCount = 0

default symbols × 1D,4H,8H after fill:
requiredCount = 174
rawReadyCount = 36
rawMissingCount = 138
cleanReadyCount = 36
cleanMissingCount = 138
```

### 备注
- 当前本地已覆盖 12 个 symbols 的 `1D/4H/8H`:BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK, AVAX, TON, TRX, DOT。
- 后续继续每批 5 个 symbols 补齐,可控制 OKX 下载耗时和失败半径。

---

## 25. Python Data Pipeline Small Batch Fill 3

**状态:✅ 通过**

### 命令
```bash
uv run python -m backend_py.run_full_pipeline --check-inputs --symbols BCH-USDT LTC-USDT UNI-USDT AAVE-USDT NEAR-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_data_pipeline --missing-only --symbols BCH-USDT LTC-USDT UNI-USDT AAVE-USDT NEAR-USDT --bars 1D,4H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --symbols BCH-USDT LTC-USDT UNI-USDT AAVE-USDT NEAR-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
```

### 期望
- 第三批补齐 `BCH/LTC/UNI/AAVE/NEAR × 1D/4H`。
- 补齐后 `python_full --skip-download` 可验证该批 1D/4H/8H 全链路。
- 本地覆盖度从 36 组提升到 51 组。

### 实际
```
BCH/LTC/UNI/AAVE/NEAR × 1D/4H:
stepCount = 10
successCount = 10
errorCount = 0

rawRows / cleanRows:
BCH 1D = 2754 / 2753
LTC 1D = 3066 / 3065
UNI 1D = 2086 / 2085
AAVE 1D = 2051 / 2050
NEAR 1D = 2009 / 2008
BCH 4H = 16516 / 16515
LTC 4H = 18387 / 18386
UNI 4H = 12509 / 12508
AAVE 4H = 12298 / 12297
NEAR 4H = 12046 / 12045

python_full BCH/LTC/UNI/AAVE/NEAR × 1D,4H,8H:
successCount = 15
weatherCount = 15
errorCount = 0

default symbols × 1D,4H,8H after fill:
requiredCount = 174
rawReadyCount = 51
rawMissingCount = 123
cleanReadyCount = 51
cleanMissingCount = 123
```

### 备注
- 当前本地已覆盖 17 个 symbols 的 `1D/4H/8H`:BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK, AVAX, TON, TRX, DOT, BCH, LTC, UNI, AAVE, NEAR。
- 继续分批补齐剩余 41 个 symbols。

---

## 26. Python Data Pipeline Small Batch Fill 4

**状态:✅ 通过**

### 命令
```bash
uv run python -m backend_py.run_full_pipeline --check-inputs --symbols OP-USDT ARB-USDT SUI-USDT APT-USDT FIL-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_data_pipeline --missing-only --symbols OP-USDT ARB-USDT SUI-USDT APT-USDT FIL-USDT --bars 1D,4H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --symbols OP-USDT ARB-USDT SUI-USDT APT-USDT FIL-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
```

### 期望
- 第四批补齐 `OP/ARB/SUI/APT/FIL × 1D/4H`。
- 补齐后 `python_full --skip-download` 可验证该批 1D/4H/8H 全链路。
- 本地覆盖度从 51 组提升到 66 组。

### 实际
```
OP/ARB/SUI/APT/FIL × 1D/4H:
stepCount = 10
successCount = 10
errorCount = 0

rawRows / cleanRows:
OP 1D = 1464 / 1463
ARB 1D = 1169 / 1168
SUI 1D = 1128 / 1127
APT 1D = 1324 / 1323
FIL 1D = 2009 / 2008
OP 4H = 8779 / 8778
ARB 4H = 7004 / 7003
SUI 4H = 6758 / 6757
APT 4H = 7937 / 7936
FIL 4H = 12046 / 12045

python_full OP/ARB/SUI/APT/FIL × 1D,4H,8H:
successCount = 15
weatherCount = 15
errorCount = 0

default symbols × 1D,4H,8H after fill:
requiredCount = 174
rawReadyCount = 66
rawMissingCount = 108
cleanReadyCount = 66
cleanMissingCount = 108
```

### 备注
- 当前本地已覆盖 22 个 symbols 的 `1D/4H/8H`:BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK, AVAX, TON, TRX, DOT, BCH, LTC, UNI, AAVE, NEAR, OP, ARB, SUI, APT, FIL。
- 继续分批补齐剩余 36 个 symbols。

---

## 27. Python Data Pipeline Small Batch Fill 5

**状态:✅ 通过**

### 命令
```bash
uv run python -m backend_py.run_full_pipeline --check-inputs --symbols ETC-USDT ATOM-USDT INJ-USDT STX-USDT IMX-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_data_pipeline --missing-only --symbols ETC-USDT ATOM-USDT INJ-USDT STX-USDT IMX-USDT --bars 1D,4H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --symbols ETC-USDT ATOM-USDT INJ-USDT STX-USDT IMX-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
```

### 期望
- 第五批补齐 `ETC/ATOM/INJ/STX/IMX × 1D/4H`。
- 补齐后 `python_full --skip-download` 可验证该批 1D/4H/8H 全链路。
- 本地覆盖度从 66 组提升到 81 组。

### 实际
```
ETC/ATOM/INJ/STX/IMX × 1D/4H:
stepCount = 10
successCount = 10
errorCount = 0

rawRows / cleanRows:
ETC 1D = 3066 / 3065
ATOM 1D = 2599 / 2598
INJ 1D = 917 / 916
STX 1D = 1918 / 1917
IMX 1D = 1672 / 1671
ETC 4H = 18387 / 18386
ATOM 4H = 15585 / 15584
INJ 4H = 5493 / 5492
STX 4H = 11499 / 11498
IMX 4H = 10022 / 10021

python_full ETC/ATOM/INJ/STX/IMX × 1D,4H,8H:
successCount = 15
weatherCount = 15
errorCount = 0

default symbols × 1D,4H,8H after fill:
requiredCount = 174
rawReadyCount = 81
rawMissingCount = 93
cleanReadyCount = 81
cleanMissingCount = 93
```

### 备注
- 当前本地已覆盖 27 个 symbols 的 `1D/4H/8H`:BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK, AVAX, TON, TRX, DOT, BCH, LTC, UNI, AAVE, NEAR, OP, ARB, SUI, APT, FIL, ETC, ATOM, INJ, STX, IMX。
- 继续分批补齐剩余 31 个 symbols。

---

## 28. Python Data Pipeline Small Batch Fill 6

**状态:✅ 通过**

### 命令
```bash
uv run python -m backend_py.run_full_pipeline --check-inputs --symbols WLD-USDT AR-USDT XLM-USDT ICP-USDT HBAR-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_data_pipeline --missing-only --symbols WLD-USDT AR-USDT XLM-USDT ICP-USDT HBAR-USDT --bars 1D,4H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --symbols WLD-USDT AR-USDT XLM-USDT ICP-USDT HBAR-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
```

### 期望
- 第六批补齐 `WLD/AR/XLM/ICP/HBAR × 1D/4H`。
- 补齐后 `python_full --skip-download` 可验证该批 1D/4H/8H 全链路。
- 本地覆盖度从 81 组提升到 96 组。

### 实际
```
WLD/AR/XLM/ICP/HBAR × 1D/4H:
stepCount = 10
successCount = 10
errorCount = 0

rawRows / cleanRows:
WLD 1D = 1046 / 1045
AR 1D = 1623 / 1622
XLM 1D = 3066 / 3065
ICP 1D = 1850 / 1849
HBAR 1D = 2452 / 2451
WLD 4H = 6267 / 6266
AR 4H = 9728 / 9727
XLM 4H = 18387 / 18386
ICP 4H = 11095 / 11094
HBAR 4H = 14703 / 14702

python_full WLD/AR/XLM/ICP/HBAR × 1D,4H,8H:
successCount = 15
weatherCount = 15
errorCount = 0

default symbols × 1D,4H,8H after fill:
requiredCount = 174
rawReadyCount = 96
rawMissingCount = 78
cleanReadyCount = 96
cleanMissingCount = 78
```

### 备注
- 当前本地已覆盖 32 个 symbols 的 `1D/4H/8H`:BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK, AVAX, TON, TRX, DOT, BCH, LTC, UNI, AAVE, NEAR, OP, ARB, SUI, APT, FIL, ETC, ATOM, INJ, STX, IMX, WLD, AR, XLM, ICP, HBAR。
- 继续分批补齐剩余 26 个 symbols。

---

## 29. Python Data Pipeline Small Batch Fill 7

**状态:✅ 通过**

### 命令
```bash
uv run python -m backend_py.run_full_pipeline --check-inputs --symbols ALGO-USDT LDO-USDT CRV-USDT ENS-USDT PENDLE-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_data_pipeline --missing-only --symbols ALGO-USDT LDO-USDT CRV-USDT ENS-USDT PENDLE-USDT --bars 1D,4H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --symbols ALGO-USDT LDO-USDT CRV-USDT ENS-USDT PENDLE-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
```

### 期望
- 第七批补齐 `ALGO/LDO/CRV/ENS/PENDLE × 1D/4H`。
- 补齐后 `python_full --skip-download` 可验证该批 1D/4H/8H 全链路。
- 本地覆盖度从 96 组提升到 111 组。

### 实际
```
ALGO/LDO/CRV/ENS/PENDLE × 1D/4H:
stepCount = 10
successCount = 10
errorCount = 0

rawRows / cleanRows:
ALGO 1D = 2544 / 2543
LDO 1D = 1371 / 1370
CRV 1D = 2120 / 2119
ENS 1D = 1668 / 1667
PENDLE 1D = 615 / 614
ALGO 4H = 15233 / 15232
LDO 4H = 8217 / 8216
CRV 4H = 12712 / 12711
ENS 4H = 10001 / 10000
PENDLE 4H = 3682 / 3681

python_full ALGO/LDO/CRV/ENS/PENDLE × 1D,4H,8H:
successCount = 15
weatherCount = 15
errorCount = 0

default symbols × 1D,4H,8H after fill:
requiredCount = 174
rawReadyCount = 111
rawMissingCount = 63
cleanReadyCount = 111
cleanMissingCount = 63
```

### 备注
- 当前本地已覆盖 37 个 symbols 的 `1D/4H/8H`:BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK, AVAX, TON, TRX, DOT, BCH, LTC, UNI, AAVE, NEAR, OP, ARB, SUI, APT, FIL, ETC, ATOM, INJ, STX, IMX, WLD, AR, XLM, ICP, HBAR, ALGO, LDO, CRV, ENS, PENDLE。
- 继续分批补齐剩余 21 个 symbols。

---

## 30. Python Data Pipeline Small Batch Fill 8

**状态:✅ 通过**

### 命令
```bash
uv run python -m backend_py.run_full_pipeline --check-inputs --symbols JUP-USDT PYTH-USDT TIA-USDT ONDO-USDT FET-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_data_pipeline --missing-only --symbols JUP-USDT PYTH-USDT TIA-USDT ONDO-USDT FET-USDT --bars 1D,4H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --symbols JUP-USDT PYTH-USDT TIA-USDT ONDO-USDT FET-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
```

### 期望
- 第八批补齐 `JUP/PYTH/TIA/ONDO/FET × 1D/4H`。
- 补齐后 `python_full --skip-download` 可验证该批 1D/4H/8H 全链路。
- 本地覆盖度从 111 组提升到 126 组。

### 实际
```
JUP/PYTH/TIA/ONDO/FET × 1D/4H:
stepCount = 10
successCount = 10
errorCount = 0

rawRows / cleanRows:
JUP 1D = 855 / 854
PYTH 1D = 927 / 926
TIA 1D = 946 / 945
ONDO 1D = 675 / 674
FET 1D = 923 / 922
JUP 4H = 5120 / 5119
PYTH 4H = 5552 / 5551
TIA 4H = 5671 / 5670
ONDO 4H = 4041 / 4040
FET 4H = 5529 / 5528

python_full JUP/PYTH/TIA/ONDO/FET × 1D,4H,8H:
successCount = 15
weatherCount = 15
errorCount = 0

default symbols × 1D,4H,8H after fill:
requiredCount = 174
rawReadyCount = 126
rawMissingCount = 48
cleanReadyCount = 126
cleanMissingCount = 48
```

### 备注
- 当前本地已覆盖 42 个 symbols 的 `1D/4H/8H`:BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK, AVAX, TON, TRX, DOT, BCH, LTC, UNI, AAVE, NEAR, OP, ARB, SUI, APT, FIL, ETC, ATOM, INJ, STX, IMX, WLD, AR, XLM, ICP, HBAR, ALGO, LDO, CRV, ENS, PENDLE, JUP, PYTH, TIA, ONDO, FET。
- 继续分批补齐剩余 16 个 symbols。

---

## 31. Python Data Pipeline Small Batch Fill 9

**状态:✅ 通过**

### 命令
```bash
uv run python -m backend_py.run_full_pipeline --check-inputs --symbols PEPE-USDT SHIB-USDT BONK-USDT FLOKI-USDT WIF-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_data_pipeline --missing-only --symbols PEPE-USDT SHIB-USDT BONK-USDT FLOKI-USDT WIF-USDT --bars 1D,4H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --symbols PEPE-USDT SHIB-USDT BONK-USDT FLOKI-USDT WIF-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
```

### 期望
- 第九批补齐 `PEPE/SHIB/BONK/FLOKI/WIF × 1D/4H`。
- 补齐后 `python_full --skip-download` 可验证该批 1D/4H/8H 全链路。
- 本地覆盖度从 126 组提升到 141 组。

### 实际
```
PEPE/SHIB/BONK/FLOKI/WIF × 1D/4H:
stepCount = 10
successCount = 10
errorCount = 0

rawRows / cleanRows:
PEPE 1D = 1130 / 1129
SHIB 1D = 1853 / 1852
BONK 1D = 878 / 877
FLOKI 1D = 1266 / 1265
WIF 1D = 780 / 779
PEPE 4H = 6771 / 6770
SHIB 4H = 11110 / 11109
BONK 4H = 5260 / 5259
FLOKI 4H = 7587 / 7586
WIF 4H = 4671 / 4670

python_full PEPE/SHIB/BONK/FLOKI/WIF × 1D,4H,8H:
successCount = 15
weatherCount = 15
insufficientHistoryCount = 0
errorCount = 0

default symbols × 1D,4H,8H after fill:
requiredCount = 174
rawReadyCount = 141
rawMissingCount = 33
cleanReadyCount = 141
cleanMissingCount = 33
```

### 备注
- 当前本地已覆盖 47 个 symbols 的 `1D/4H/8H`:BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK, AVAX, TON, TRX, DOT, BCH, LTC, UNI, AAVE, NEAR, OP, ARB, SUI, APT, FIL, ETC, ATOM, INJ, STX, IMX, WLD, AR, XLM, ICP, HBAR, ALGO, LDO, CRV, ENS, PENDLE, JUP, PYTH, TIA, ONDO, FET, PEPE, SHIB, BONK, FLOKI, WIF。
- 继续分批补齐剩余 11 个 symbols。

---

## 32. Python Data Pipeline Small Batch Fill 10

**状态:✅ 通过**

### 命令
```bash
uv run python -m backend_py.run_full_pipeline --check-inputs --symbols ORDI-USDT SATS-USDT NOT-USDT ENA-USDT W-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_data_pipeline --missing-only --symbols ORDI-USDT SATS-USDT NOT-USDT ENA-USDT W-USDT --bars 1D,4H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --symbols ORDI-USDT SATS-USDT NOT-USDT ENA-USDT W-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
```

### 期望
- 第十批补齐 `ORDI/SATS/NOT/ENA/W × 1D/4H`。
- 补齐后 `python_full --skip-download` 可验证该批 1D/4H/8H 全链路。
- 本地覆盖度从 141 组提升到 156 组。

### 实际
```
ORDI/SATS/NOT/ENA/W × 1D/4H:
stepCount = 10
successCount = 10
errorCount = 0

rawRows / cleanRows:
ORDI 1D = 1111 / 1110
SATS 1D = 899 / 898
NOT 1D = 749 / 748
ENA 1D = 260 / 259
W 1D = 792 / 791
ORDI 4H = 6656 / 6655
SATS 4H = 5385 / 5384
NOT 4H = 4484 / 4483
ENA 4H = 1552 / 1551
W 4H = 4742 / 4741

python_full ORDI/SATS/NOT/ENA/W × 1D,4H,8H:
successCount = 15
weatherCount = 15
insufficientHistoryCount = 0
errorCount = 0

default symbols × 1D,4H,8H after fill:
requiredCount = 174
rawReadyCount = 156
rawMissingCount = 18
cleanReadyCount = 156
cleanMissingCount = 18
```

### 备注
- 当前本地已覆盖 52 个 symbols 的 `1D/4H/8H`:BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK, AVAX, TON, TRX, DOT, BCH, LTC, UNI, AAVE, NEAR, OP, ARB, SUI, APT, FIL, ETC, ATOM, INJ, STX, IMX, WLD, AR, XLM, ICP, HBAR, ALGO, LDO, CRV, ENS, PENDLE, JUP, PYTH, TIA, ONDO, FET, PEPE, SHIB, BONK, FLOKI, WIF, ORDI, SATS, NOT, ENA, W。
- `ENA` 日线历史较短,但 `python_full` 未出现 insufficient-history 或 error。
- 继续分批补齐剩余 6 个 symbols。

---

## 33. Python Data Pipeline Final Batch and Full Default Validation

**状态:✅ 通过**

### 命令
```bash
uv run python -m backend_py.run_full_pipeline --check-inputs --symbols STRK-USDT ZK-USDT ZRO-USDT GALA-USDT SAND-USDT MANA-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_data_pipeline --missing-only --symbols STRK-USDT ZK-USDT ZRO-USDT GALA-USDT SAND-USDT MANA-USDT --bars 1D,4H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --symbols STRK-USDT ZK-USDT ZRO-USDT GALA-USDT SAND-USDT MANA-USDT --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --bars 1D,4H,8H --days 3650
```

### 期望
- 最后一批补齐 `STRK/ZK/ZRO/GALA/SAND/MANA × 1D/4H`。
- 补齐后 `python_full --skip-download` 可验证该批 1D/4H/8H 全链路。
- 本地输入覆盖度从 156 组提升到 174 组。
- 完整 default symbols 的 `python_full` 验证可覆盖 58 个 symbols × 1D/4H/8H。

### 实际
```
STRK/ZK/ZRO/GALA/SAND/MANA × 1D/4H:
stepCount = 12
successCount = 12
errorCount = 0

rawRows / cleanRows:
STRK 1D = 835 / 834
ZK 1D = 716 / 715
ZRO 1D = 714 / 713
GALA 1D = 1716 / 1715
SAND 1D = 1904 / 1903
MANA 1D = 3066 / 3065
STRK 4H = 5000 / 4999
ZK 4H = 4287 / 4286
ZRO 4H = 4274 / 4273
GALA 4H = 10287 / 10286
SAND 4H = 11415 / 11414
MANA 4H = 18387 / 18386

python_full STRK/ZK/ZRO/GALA/SAND/MANA × 1D,4H,8H:
successCount = 18
weatherCount = 18
insufficientHistoryCount = 0
errorCount = 0

default symbols × 1D,4H,8H after fill:
requiredCount = 174
rawReadyCount = 174
rawMissingCount = 0
cleanReadyCount = 174
cleanMissingCount = 0

full default python_full × 1D,4H,8H:
successCount = 174
weatherCount = 174
insufficientHistoryCount = 0
errorCount = 0
1D successCount = 58
4H successCount = 58
8H successCount = 58
```

### 备注
- 当前本地已覆盖全部 58 个 default symbols 的 `1D/4H/8H`:BTC, ETH, SOL, BNB, XRP, DOGE, ADA, LINK, AVAX, TON, TRX, DOT, BCH, LTC, UNI, AAVE, NEAR, OP, ARB, SUI, APT, FIL, ETC, ATOM, INJ, STX, IMX, WLD, AR, XLM, ICP, HBAR, ALGO, LDO, CRV, ENS, PENDLE, JUP, PYTH, TIA, ONDO, FET, PEPE, SHIB, BONK, FLOKI, WIF, ORDI, SATS, NOT, ENA, W, STRK, ZK, ZRO, GALA, SAND, MANA。
- 本地 default input coverage 已完成:raw/clean 均为 `174/174`。
- 完整 default `python_full --skip-download` 已通过,下一步可进入 `--official` cutover checklist 和生产报告 writer 切换准备。

---

## 34. Python Official Cutover Preflight

**状态:✅ 通过**

### 命令
```bash
uv run python -m py_compile backend_py/*.py backend_py/research/*.py
uv run python -m backend_py.run_full_pipeline --plan-outputs --official --skip-download --bars 1D,4H,8H --days 3650
uv run python -m backend_py.smoke_test
node --check app.js
node --check server.mjs
```

### 期望
- `run_full_pipeline` 支持 `--plan-outputs`,可在不写入 report 的情况下列出 official writer 影响面。
- official output plan 使用空 suffix,匹配正式 report 文件名。
- preflight 不覆盖 `reports/` 中任何正式产物。
- smoke test 覆盖新的 output-plan 解析和路径计数。

### 实际
```
python compile = pass
node --check app.js = pass
node --check server.mjs = pass
smoke_test = pass

official output plan:
pathCount = 1748
existingCount = 1350
missingCount = 398
official = true
suffix = ""
```

### 备注
- 新增 `docs/python-official-cutover-checklist.md`,记录 official cutover 的 preflight、执行、post-check 和 rollback。
- 本轮只新增 preflight 能力和 checklist,未执行 `python_full --official`,因此没有覆盖正式 tracked reports。
- 下一步若执行 cutover,命令为 `uv run python -m backend_py.run_full_pipeline --skip-download --official --bars 1D,4H,8H --days 3650`。

---

## 35. Python Official Report Cutover

**状态:✅ 通过**

### 命令
```bash
git status --short --branch
uv run python -m backend_py.run_full_pipeline --check-inputs --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --plan-outputs --official --skip-download --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --bars 1D,4H,8H --days 3650
uv run python -m backend_py.run_full_pipeline --skip-download --official --bars 1D,4H,8H --days 3650
uv run python -m backend_py.smoke_test
uv run python -m py_compile backend_py/*.py backend_py/research/*.py
node --check app.js
node --check server.mjs
```

### 期望
- official cutover 前 input coverage 仍为 `174/174`。
- official output plan 使用空 suffix,并明确 report 写入影响面。
- 非 official full validation 先通过,再执行 official writer。
- official writer 覆盖正式 `reports/` 后,API smoke test 与 Node syntax check 仍通过。

### 实际
```
input coverage:
requiredCount = 174
rawReadyCount = 174
rawMissingCount = 0
cleanReadyCount = 174
cleanMissingCount = 0

official output plan:
pathCount = 1748
existingCount = 1350
missingCount = 398
official = true
suffix = ""

preflight python_full:
successCount = 174
weatherCount = 174
insufficientHistoryCount = 0
errorCount = 0
official = false
suffix = _py_full

official python_full:
successCount = 174
weatherCount = 174
insufficientHistoryCount = 0
errorCount = 0
official = true
suffix = ""
1D successCount = 58
4H successCount = 58
8H successCount = 58

official combined report metadata:
rowCount = 174
symbolCount = 58
bars = 1D, 4H, 8H
skipDownload = true
summaryOnly = false
fromReports = false

post-cutover checks:
smoke_test = pass
py_compile = pass
node --check app.js = pass
node --check server.mjs = pass

reports git status:
modified tracked reports = 1346
new official reports = 228
```

### 备注
- Python full pipeline 已正式写入 production report 文件名。
- 当前 official combined report 只包含已完成覆盖的 `1D/4H/8H`;旧的 `1W` report 文件仍在仓库中,但不再出现在本次 official combined summary。
- 下一步应审查 official reports diff,再切换/收敛 Node scanner/orchestrator 入口。

---

## 36. Python Official Scanner Entry Cutover

**状态:✅ 通过**

### 命令
```bash
git status --short --branch
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.smoke_test
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m py_compile backend_py/*.py backend_py/research/*.py
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check app.js
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check server.mjs
```

### 期望
- `/api/scanner/run?mode=full` 不再调用 Node `multi:periods`,改为 Python official full pipeline。
- `full` 默认使用 `--skip-download --official --days 3650 --bars 1D,4H,8H`。
- legacy Node full scanner 以显式 `node_full` 模式保留。
- smoke test 覆盖 `full` 与 `node_full` 的命令映射。

### 实际
```
full command = backend_py.run_full_pipeline --skip-download --official --days 3650 --bars 1D,4H,8H
node_full command = npm run multi:periods
smoke_test = pass
py_compile = pass
node --check app.js = pass
node --check server.mjs = pass
```

### 备注
- 本轮只切换 scanner/API 入口和文档,未重新生成 official reports。
- 当前 Codex shell 未默认包含用户本机 `uv/npm` PATH,验证时显式加入 `/Users/guanlan/.local/bin` 与 Node `bin`。

---

## 37. Python Official Summary Entry Cutover

**状态:✅ 通过**

### 命令
```bash
git status --short --branch
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.smoke_test
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m py_compile backend_py/*.py backend_py/research/*.py
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check app.js
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check server.mjs
```

### 期望
- `/api/scanner/run?mode=summary` 不再调用 Node `multi:periods --from-reports --summary-only`,改为 Python official summary-only pipeline。
- `summary` 默认使用 `--from-reports --summary-only --skip-download --official --days 3650 --bars 1D,4H,8H`。
- legacy Node summary scanner 以显式 `node_summary` 模式保留。
- smoke test 覆盖 `summary`、`node_summary`、`full` 与 `node_full` 的命令映射。

### 实际
```
summary command = backend_py.run_full_pipeline --from-reports --summary-only --skip-download --official --days 3650 --bars 1D,4H,8H
node_summary command = npm run multi:periods -- --from-reports --summary-only
smoke_test = pass
py_compile = pass
node --check app.js = pass
node --check server.mjs = pass
```

### 备注
- 本轮只切换 scanner/API summary 入口和文档,未执行 summary rebuild,因此未重新生成 official reports。
- `node_summary` 与 `node_full` 作为 legacy 回退入口暂时保留。

---

## 38. Python Official Package Script Cutover

**状态:✅ 通过**

### 命令
```bash
git status --short --branch
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.smoke_test
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m py_compile backend_py/*.py backend_py/research/*.py
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check app.js
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check server.mjs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check scripts/run-multi-symbol-1d.mjs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" npm --silent run multi:1d -- --plan-outputs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" npm --silent run multi:summary -- --plan-outputs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" npm --silent run multi:periods -- --plan-outputs
```

### 期望
- `npm run multi:1d` 指向 Python official 1D full pipeline。
- `npm run multi:summary` 指向 Python official summary-only pipeline。
- `npm run multi:periods` 指向 Python official full pipeline。
- 旧 Node 多周期脚本移动到 `legacy:multi:*`。
- API 的 `node_summary` / `node_full` 回退入口调用 `legacy:multi:periods`。
- package script preflight 只输出 plan,不写入 official reports。

### 实际
```
multi:1d plan:
step = python-full-output-plan
official = true
suffix = ""
summaryOnly = false
fromReports = false
pathCount = 584
existingCount = 584
missingCount = 0

multi:summary plan:
step = python-full-output-plan
official = true
suffix = ""
summaryOnly = true
fromReports = true
pathCount = 8
existingCount = 8
missingCount = 0

multi:periods plan:
step = python-full-output-plan
official = true
suffix = ""
summaryOnly = false
fromReports = false
pathCount = 1748
existingCount = 1748
missingCount = 0

smoke_test = pass
py_compile = pass
node checks = pass
```

### 备注
- 本轮只改 package scripts、API legacy 回退命令、测试和文档,未重新生成 official reports。
- `legacy:multi:periods` 暂时保留旧 `4H,8H,1D,1W` Node 范围;当前 Python official 主路径仍是 `1D,4H,8H`。

---

## 39. Python Data Package Script Cutover

**状态:✅ 通过**

### 命令
```bash
git status --short --branch
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.smoke_test
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m py_compile backend_py/*.py backend_py/research/*.py
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check app.js
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check server.mjs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check scripts/download-data.mjs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check scripts/clean-data.mjs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" npm --silent run download -- --max-symbols 0
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" npm --silent run clean -- --max-symbols 0
```

### 期望
- `npm run download` 指向 Python `backend_py.run_data_pipeline --download-only`。
- `npm run clean` 指向 Python `backend_py.run_data_pipeline --clean-only`。
- 旧 Node 数据脚本移动到 `legacy:download` / `legacy:clean`。
- no-write CLI 检查使用 `--max-symbols 0`,不下载、不清洗、不写 data。

### 实际
```
download no-write:
step = python-data-pipeline
stepCount = 0
successCount = 0
skippedCount = 0
errorCount = 0

clean no-write:
step = python-data-pipeline
stepCount = 0
successCount = 0
skippedCount = 0
errorCount = 0

smoke_test = pass
py_compile = pass
node checks = pass
```

### 备注
- 本轮只改 package scripts、测试和文档,未下载数据,未重写 `data/raw` 或 `data/clean`。
- `download:macro` 暂时仍是 Node 宏观数据入口,尚未迁移。

---

## 40. Python Single-Symbol Research Script Cutover

**状态:✅ 通过**

### 命令
```bash
git status --short --branch
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.smoke_test
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m py_compile backend_py/*.py backend_py/research/*.py
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check app.js
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check server.mjs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check scripts/build-feature-factory.mjs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check scripts/build-deviation-rules.mjs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check scripts/build-market-weather-router.mjs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" npm --silent run features -- --instrument BTC-USDT --bar 1D --plan-outputs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" npm --silent run rules:deviations -- --instrument BTC-USDT --bar 1D --plan-outputs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" npm --silent run weather:router -- --instrument BTC-USDT --bar 1D --plan-outputs
```

### 期望
- `npm run features` 指向 Python `backend_py.build_feature_factory --official`。
- `npm run rules:deviations` 指向 Python `backend_py.build_deviation_rules --official`。
- `npm run weather:router` 指向 Python `backend_py.build_market_weather_router --official`。
- 旧 Node 单品种研究脚本移动到 `legacy:features` / `legacy:rules:deviations` / `legacy:weather:router`。
- `--plan-outputs` 只列出输出计划,不写入 reports。

### 实际
```
features plan:
step = build-feature-factory-output-plan
official = true
suffix = ""
pathCount = 2
existingCount = 2
missingCount = 0

rules:deviations plan:
step = build-deviation-rules-output-plan
official = true
suffix = ""
pathCount = 3
existingCount = 3
missingCount = 0

weather:router plan:
step = build-market-weather-router-output-plan
official = true
suffix = ""
pathCount = 6
existingCount = 5
missingCount = 1

smoke_test = pass
py_compile = pass
node checks = pass
```

### 备注
- 本轮只改 Python CLI official/preflight 能力、package scripts、测试和文档,未重新生成 official reports。
- `weather:router` 的 missing output 是 standalone router observations CSV;旧 Node standalone router 也会生成该类输出。

---

## 41. Remaining Node Command Inventory

**状态:✅ 通过**

### 命令
```bash
git status --short --branch
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.smoke_test
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m py_compile backend_py/*.py backend_py/research/*.py
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check app.js
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check server.mjs
python3 - <<'PY'
import json
p=json.load(open("package.json"))
print("\\n".join(sorted(k for k,v in p["scripts"].items() if v.startswith("node "))))
PY
```

### 期望
- 剩余 Node package scripts 被明确分类为 legacy fallback、静态服务、研究/训练工具。
- `backend_py.smoke_test` 断言当前允许保留的 Node script 集合。
- 新增文档 `docs/remaining-node-command-inventory.md` 作为后续移除 Node 的工作清单。

### 实际
```
remaining node scripts:
backtest:deviations
backtest:indicators
backtest:position
backtest:router
backtest:volatility
calibrate:router
compare:macro
download:macro
journal:create
legacy:clean
legacy:download
legacy:features
legacy:multi:1d
legacy:multi:periods
legacy:multi:weather
legacy:rules:deviations
legacy:weather:router
serve
train:state
train:trees
validate:trees

smoke_test = pass
py_compile = pass
node checks = pass
```

### 备注
- 本轮只新增剩余 Node 命令盘点和测试白名单,未修改 reports/data。
- 推荐迁移顺序: `calibrate:router`/`backtest:router` -> macro commands -> training commands -> historical backtests/journal -> optional `serve` cleanup。

---

## 42. Python Router Backtest And Calibration Script Cutover

**状态:✅ 通过**

### 命令
```bash
git status --short --branch
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.smoke_test
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m py_compile backend_py/*.py backend_py/research/*.py
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check app.js
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check server.mjs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check scripts/backtest-strategy-router.mjs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check scripts/calibrate-router.mjs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" npm --silent run backtest:router -- --instrument BTC-USDT --bar 1D --plan-outputs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" npm --silent run calibrate:router -- --instrument BTC-USDT --bar 1D --plan-outputs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.backtest_strategy_router --instrument BTC-USDT --bar 1D --days 3650
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.calibrate_router --instrument BTC-USDT --bar 1D --days 3650
```

### 期望
- `npm run backtest:router` 指向 Python `backend_py.backtest_strategy_router --official`。
- `npm run calibrate:router` 指向 Python `backend_py.calibrate_router --official`。
- 旧 Node router research scripts 移动到 `legacy:backtest:router` / `legacy:calibrate:router`。
- Python router backtest 输出 `summaryRows` 与 `observationRows`。
- Python calibration metadata 包含 `calibration` 说明和 `currentSignals`。
- 非 official 实跑只写 `_py` 对照产物,不覆盖 official reports。

### 实际
```
backtest:router plan:
step = backtest-strategy-router-output-plan
official = true
suffix = ""
pathCount = 3
existingCount = 2
missingCount = 1

calibrate:router plan:
step = calibrate-router-output-plan
official = true
suffix = ""
pathCount = 3
existingCount = 3
missingCount = 0

non-official backtest run:
summaryRows = 128
observationRows = 93416
routeCount = 8

non-official calibration run:
calibrationRows = 32
currentSignals = 8
observationRows = 93416

remaining node scripts no longer include:
backtest:router
calibrate:router

smoke_test = pass
py_compile = pass
node checks = pass
```

### 备注
- 本轮新增 `backend_py.backtest_strategy_router` 与 `backend_py.calibrate_router`。
- 新增 `_py` router research 对照产物已加入 `.gitignore`。
- `backtest:router` 的 missing official path 是 standalone strategy router observations CSV;旧 Node standalone router backtest 也会生成该类输出。

---

## 43. Python Macro Data Script Cutover

**状态:✅ 通过**

### 命令
```bash
git status --short --branch
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.smoke_test
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m py_compile backend_py/*.py backend_py/research/*.py
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check scripts/download-macro-data.mjs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check app.js
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check server.mjs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" npm --silent run download:macro -- --instrument BTC-USDT --bar 1D --plan-outputs
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python - <<'PY'
from backend_py.research.macro_data import build_macro_feature_rows, parse_fred_csv, macro_rows_to_csv_rows
source = {"key": "dollarIndex"}
fred = parse_fred_csv("DATE,DTWEXBGS\n2024-01-01,100\n2024-01-22,105\n", source)
rows = build_macro_feature_rows(["2024-01-01", "2024-01-22"], {"dollarIndex": fred})
print({"fredRows": len(fred), "rows": len(rows), "lastDollar": rows[-1]["macroDollarIndex"], "csvKeys": list(macro_rows_to_csv_rows(rows)[-1].keys())[:3]})
PY
```

### 期望
- `npm run download:macro` 指向 Python `backend_py.download_macro_data`。
- 旧 Node macro data script 移动到 `legacy:download:macro`。
- Python macro 模块覆盖 FRED CSV 解析、stablecoin chart 解析、macro feature row 构建、CSV row 输出。
- `--plan-outputs` 只列出输出计划,不下载外部 macro 数据。
- `compare:macro` 暂时继续留在 Node,等待 Python decision-tree validation/training 迁移。

### 实际
```
download:macro plan:
step = download-macro-data-output-plan
pathCount = 7
existingCount = 0
missingCount = 7

macro row sample:
fredRows = 2
rows = 2
lastDollar = 105.0
csvKeys = date, macroDollarIndex, macroDollarIndex21dChangePct

remaining node scripts no longer include:
download:macro

remaining macro node script:
compare:macro

smoke_test = pass
py_compile = pass
node checks = pass
```

### 备注
- 本轮只新增 Python macro data pipeline、package script cutover、测试和文档;未下载外部 macro 数据,未写入 `data/macro`。
- `compare:macro` 依赖 decision-tree validation,后续应和 Python ML/training stack 一起迁移。

---

## 44. Python Official Parity Gate: 1D/4H/8H Full Cutover Acceptance

**状态:✅ 通过**

### 命令
```bash
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m py_compile backend_py/research/*.py backend_py/compare_summary.py
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.build_deviation_rules --instrument AAVE-USDT --bar 1D --days 3650
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.run_full_pipeline --official --skip-download --bars 1D,4H,8H --days 3650
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node scripts/run-multi-symbol-1d.mjs --skip-download --bars 1D,4H,8H
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.run_research_parity --symbols "$SYMBOLS" --bars 1D,4H,8H --days 3650
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.run_full_pipeline --official --skip-download --bars 1D,4H,8H --days 3650
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m backend_py.smoke_test
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" uv run python -m py_compile backend_py/*.py backend_py/research/*.py
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check app.js
PATH="/Users/guanlan/.local/bin:/Users/guanlan/.local/opt/node-v24.16.0-darwin-arm64/bin:$PATH" node --check server.mjs
```

### 期望
- Python official report writer 覆盖 58 symbols x 1D/4H/8H,并与当前 Node golden 全量 parity。
- Step C `compare_feature_factory / compare_deviation_rules / compare_market_weather_router` 全部 `FAIL=0`。
- Step D `compare_summary --from-reports` `status ok`。
- 收尾后正式 `reports/` 保持修复后的 Python official,不留下临时 Node golden 或 `_py` 影子。
- 1W 不纳入本次范围;1W 缺 raw/clean 数据,单开后续下载和验收任务。

### 实际
```
js_round 单点:
SOL-USDT 8H ruleLibraryRows[5].medianPositionPct: 50.49 -> 50.48 (= Node)

js_sum 单点:
DOGE-USDT 4H featureStats.maDeviationAtr.mean = 2602.7060855431077
DOGE-USDT 4H featureStats.maDeviationAtr.std = 49385.167585555624
DOGE-USDT 4H featureStats.maPositionPct.mean = 16.582441233142003
DOGE-USDT 4H featureStats.stretchHeat.mean = 55.435550256353814
DOGE-USDT 4H featureStats.stretchHeat.std = 8.41901621804308

js_number_to_string 单点:
AAVE-USDT 1D finalWeather.bigCycle = 大周期偏弱，10日继续远离概率 54% (= Node)

Python official regenerate:
successCount = 174
errorCount = 0

Node golden regenerate:
successCount = 174
errorCount = 0

Full parity:
overallSuccessCount = 1046
overallErrorCount = 0
Step C PASS = 522
Step C FAIL = 0
Summary status = ok
Summary rowCount = 174
Summary errorCount = 0
Summary weightedWeatherCount = 120.83

Python official restore:
successCount = 174
errorCount = 0

smoke_test:
health = ok
rowCount = 174
symbolCount = 58
scannerMode = python_orchestrator
dashboardCandlesStatus = ok

py_compile = pass
node --check app.js = pass
node --check server.mjs = pass
```

### 备注
- 本轮修复三类 parity helper 差异:
  - `js_round`:忠实复刻 Node `Number(value.toFixed(digits))` 在 `.xx5` 边界上的行为。
  - `js_sum`:故意使用 JS-style 左到右朴素累加,避免 CPython 3.12+ `sum()` 补偿求和改变 ULP。
  - `js_number_to_string`:finalWeather 概率文案复刻 JS Number 字符串化,整数概率不保留 `.0`。
- `compare_summary` 忽略 `skipDownload / summaryOnly / fromReports` 三个生成模式 metadata;这些是产物出身标记,不是市场数据。summary rows 与聚合值仍严格比较。
- `reports/` 已落回修复后的 Python official;临时 Node golden 和 `_py` 影子均未保留。
- 1W 本次未纳入:本地 1W raw/clean 数据缺失,后续应单独执行下载 1W data -> Python official 1W -> Node golden parity -> default bars/combined summary 收口。
