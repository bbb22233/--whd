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
