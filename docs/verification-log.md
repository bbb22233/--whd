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
