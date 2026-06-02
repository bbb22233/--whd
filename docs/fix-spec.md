# 修复规格文档 (Fix Spec)

> Quant Monitor Terminal — 基于审计清单沉淀的分步修复方案,供逐步执行。

---

## 0. 文档说明

### 0.1 目的与使用方式
本文档把一次已完成的代码审计的 17 条问题,整理成**有依赖顺序、可逐步执行**的施工方案。
执行原则:**一次只做一项,改完按该项"验证方法"自证通过,再提交,再做下一项。** 不要一次性铺开。

### 0.2 范围与约束
- 开发分支:`claude/crypto-monitor-audit-y9Qpq`。
- 一次一项,每项独立提交,提交信息引用本文件编号(如 `fix(H4): ...`)。
- 未经确认不创建 PR。

### 0.3 行号基准
- 所有行号基于 `commit 91eb0bb`("Initial quant monitor terminal")的状态。
- **重要**:每改完一步,后续文件行号会漂移。执行下一步前,以**实际文件当前内容**为准,本文行号仅作定位锚点。
- 标注 **"推测"** 的内容表示无法从代码直接确认、需执行时复核,不可当事实直接落地。

### 0.4 术语对照
| 术语 | 含义 |
|---|---|
| gate / 主灯号 | `current.gate`,最终红/黄/绿(含黄偏红、黄偏绿)结论 |
| route key 两套 | 规范引擎 `routeStrategies` 用 `trendLong/trendShort/...`(8 方向)+`trendFollowing/breakout/...`(5 聚合);主灯号 `scoreStrategies` 用 `trend/breakout/meanReversion/grid/wait`(5 family) |
| snapshot | `buildIndicatorSnapshots` 产出的单根 K 线指标快照 |
| periodWeight | 周期/历史质量权重,理应用于跨品种汇总加权 |
| 样本内 / walk-forward | 样本内=统计用了全段历史(含每个观测点之后的数据);walk-forward=严格只用观测点之前的数据 |

---

## 1. 执行顺序总表

设计原则:**数据层 → 口径层 → 聚合层 → 加权层 → 灯号层 → 训练层 → 前端层**。下游统计与灯号都消费上游数据/口径,先把数据与指标口径钉死,再动消费它们的灯号与前端。同一文件的多处改动合并到同一步,减少反复触碰与回归。

| 步骤 | 内容 | 对应审计项 | 排此位置的依赖理由 |
|---|---|---|---|
| **Step 0** | 架构决策(已拍板:**B 方案**) | H1/H2/H3/L6 走向 | 决定整个灯号层怎么改。**已决定**:接校准器取代裸魔数评分 + 统一打分系统。见 §2。 |
| **Step 1** | 下载可靠性 + 4H/8H 截断修复 | H4, L3 | 最上游。所有统计吃下载到的数据;4H/8H 被截到 ~3.6 年会让灯号在错样本上校准。两项同改 `okx.mjs`,合并。 |
| **Step 2** | 清洗规则:不再误删真实极端 K 线 | M1 | 紧跟下载。改变哪些 K 线进入管道,必须早于任何 ATR/分位重算。 |
| **Step 3** | 指标口径定稿(ATR% 分母 + 命名) | L1, L2 | L1 改 `atrPct` 波及分位/特征/SOM/灯号全链,**必须先于任何重算**。L2 同文件一起改,避免二次触碰 `indicators.mjs`。 |
| **Step 4** | 8H 聚合健壮性 | L4 | 依赖 Step 2:清洗少删 4H → 少丢整根 8H。 |
| **Step 5** | 历史质量分级与 periodWeight 真正生效 | H5 | 依赖 Step 1(截断标记)、Step 2(干净行数)才能正确判定降权,且降权要被汇总/前端真正消费。 |
| **Step 6** | 偏离研究改因果分桶 | M6 | 其产出概率会喂给灯号(`middleCloserEdge`),须在 Step 7 消费前变干净。 |
| **Step 7** | **主灯号改造(B 方案核心)** | L6 + H2 + H1 + H3 | 依赖 Step 0 决策 + 干净数据(1-6)。拆为 7a/7b/7c,见下。 |
| ┣ 7a | 打分引擎归一 | L6 | **H2 的前置**:不换引擎(`scoreStrategies`→`routeStrategies`)则查桶口径错配,接不上校准器。 |
| ┣ 7b | 接入 router-calibrator | H2 | 依赖 7a。`buildMarketWeatherRouter` 消费校准 light,重写 gate。 |
| ┗ 7c | 样本置信度并入 gate | H3 | 依赖 7b。低置信/小样本不得改色。 |
| **Step 8** | 训练层前视修复(SOM 因果归一 + 切分胜率) | M2 | 依赖 Step 3(特征值定稿)。与灯号层解耦,**可与 Step 7 并行**,但不得早于 Step 3。 |
| **Step 9** | 前端健壮性(kindKey 修正 + 空 current 优雅降级) | M4, M5 | M5 必须早于 Step 10:多品种会暴露薄历史品种 `current=null`。M4 无依赖可提前,与前端同区合并测试。 |
| **Step 10** | 前端接入多品种/多周期汇总 | M3 | 依赖 Step 5(汇总含 `periodWeight/dataStatus`)、Step 9(空数据不崩)。 |
| **Step 11** | 前端概率语境(带样本/置信展示) | L5 | 依赖 Step 10 的新汇总视图;收尾的展示层打磨。 |

**关键依赖修正(相对早期草案)**:
- 原计划把 L6(统一打分)放在灯号接线之后。经评估,**接入校准器必须同时把主灯号从 `scoreStrategies` 切到 `routeStrategies`**(否则当前分数口径与建桶口径不一致),故 L6 前置/并入 Step 7a,不能后置。
- Step 8(训练层)与 Step 7(灯号层)互不依赖,可并行,二者都只依赖 Step 1-3。

### 依赖关系简图
```
Step1(H4,L3) ─► Step2(M1) ─► Step3(L1,L2) ─┬─► Step4(L4)
                                            ├─► Step5(H5) ─────────────► Step10(M3) ─► Step11(L5)
                                            ├─► Step6(M6) ─► Step7a(L6) ─► Step7b(H2) ─► Step7c(H3)
                                            └─► Step8(M2)
Step9(M4,M5) ───────────────────────────────────────────────────────► Step10
```

---

## 2. Step 0 — 架构决策【已拍板:B 方案】

### 2.1 背景
当前主灯号 `gateFromScores`(`market-weather-router.mjs:439-456`)完全靠全局魔数阈值,而项目里已存在实现良好的 `router-calibrator`(带 `sampleConfidence`、相对基线 lift、`occurrences<30` 降级),却**从未被主灯号 import**。

### 2.2 方案 B — 接校准器取代魔数评分(**已选**)
- 做法:`buildMarketWeatherRouter` 消费 `runRouterCalibration` 的 light/lift/sampleConfidence,gate 由校准结果折叠得出;统一打分引擎到 `routeStrategies`。
- 优点:复用已验证的样本感知逻辑;红黄绿带历史校准依据;顺带统一三套打分。
- 代价:重写 gate + 换打分引擎;每品种×周期多跑一次回测,有性能成本。
- 风险:校准器是样本内统计(非 walk-forward),lift 偏乐观;质量受上游数据(H4/M1)污染——故必须排在数据层之后。

### 2.3 备选 A — 保留魔数评分,补样本置信度与归一
> 用户最终选择"接校准器+统一",对应本文档执行的就是 2.2 的方案 B 路线。保留本节仅作决策留痕。
- 做法:不接校准器,只给 `scoreStrategies`/`gateFromScores` 的趋势项做按品种归一,并把 occ/置信度并入 gate。
- 优点:改动局部,不引入回测开销。
- 代价:魔数仍在,缺历史基线对比;三套打分依旧并存。

### 2.4 选项 C(折中)
魔数归一打分 → 校准器仅做样本/基线后处理。被否(仍保留两套打分)。

### 2.5 决策记录
- **决策:接入 router-calibrator 取代裸魔数评分,并统一打分系统(对应 §2.2 方案 B 路线)。**
- 决策人:用户。
- 对后续的影响:Step 7 拆为 7a(L6 统一)+ 7b(H2 接线)+ 7c(H3 置信);H1(趋势归一)在本路线下**降级为可选**——校准器按 route 分桶对比基线已部分自归一,若 7b/7c 完成后横向灯号分布仍偏移,再回头做 H1。

---

## 3. 修复项详述

> 每项含 7 栏:① 编号标题 ② 问题(含行号)③ 影响 ④ 修复方案 ⑤ 影响范围(含"不该动")⑥ 验证方法 ⑦ 依赖。

---

### Step 1 — 数据下载

#### H4. 4H/8H 历史被分页上限截断

**② 问题**
`backtest/okx.mjs:21` 为 `while (page < 80)`,`config.mjs:5` `requestLimit: 100`(OKX history-candles 单页上限即 100)。最多 80×100=8000 根。日线 8000 根≈21 年够用;但 4H 8000 根仅 ~1333 天≈3.6 年,8H 由 4H 聚合后同样 ~3.6 年。而 `scripts/run-multi-symbol-1d.mjs:84` 默认 `days:3650`(10 年),用户以为拿到 10 年 4H,实际被悄悄截断且无告警。

**③ 影响**
4H/8H 的分位数、状态概率、校准器统计样本远少于预期,跨周期口径不一致;下游所有依赖历史分布的统计(含将接入的校准器)在 4H/8H 上系统性偏少、偏不稳。

**④ 修复方案**
- 分页上限按需要动态计算,而非写死 80:
  ```js
  // 推测:OKX 上限 limit=100;按目标天数与 bar 估算需要的页数,留冗余
  const barsPerDay = (24 * 60 * 60 * 1000) / barToMs(config.bar);
  const estimatedBars = config.days * barsPerDay;
  const maxPages = Math.ceil((estimatedBars / config.requestLimit) * 1.2) + 2;
  while (page < maxPages) { ... }
  ```
- 下载结束校验是否真的回溯到了请求起点,不足则在返回 metadata 标注:
  ```js
  const oldestReached = rows[0] ? rowTimestamp(rows[0]) : null;
  const truncated = oldestReached != null && oldestReached > startMs + barToMs(config.bar);
  return { ...payloadFields, truncated, oldestReached, requestedStartMs: startMs };
  ```
- `truncated` 标记后续供 H5 降权使用。

**⑤ 影响范围**
- 改:`backtest/okx.mjs`(`downloadOkxHistory`)。
- 顺带消费:`scripts/run-multi-symbol-1d.mjs` 的 metadata 透传(只读取新增字段,不改逻辑)。
- **不该动**:`clean.mjs`、指标/灯号(本步只修数据完整性)。

**⑥ 验证方法**
- 跑 `npm run download -- --instrument BTC-USDT --bar 4H --days 3650`,检查输出 `rowCount` 是否 ≫ 8000(10 年 4H ≈ 21900 根),`firstDate` 是否接近 10 年前。
- 对比修复前后同命令 `pageCount`/`rowCount`;断言 `truncated:false`。
- 边界:`--days 30 --bar 1D` 仍能正常少量返回,不死循环。

**⑦ 依赖**
无前置(最上游)。是 H5 与整个灯号层的前提。

---

#### L3. 下载无重试/退避,魔数分页上限

**② 问题**
`backtest/okx.mjs:28-31` 请求失败直接 `throw`;`:51` 固定 `sleep(140)`;`:21` 的 `80` 是魔数。无网络抖动容错。

**③ 影响**
批量 58 品种×4 周期时,单次瞬时网络错误就让该品种整条失败(`run-multi-symbol-1d.mjs:575-583` 记 error),数据集出现随机缺品种。

**④ 修复方案**
按项目既定 git 规范的退避策略,给单页请求加重试:
```js
async function fetchPage(url, attempt = 0) {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`OKX ${response.status} ${response.statusText}`);
    return await response.json();
  } catch (error) {
    if (attempt >= 4) throw error;
    await sleep(2000 * (2 ** attempt)); // 2s,4s,8s,16s
    return fetchPage(url, attempt + 1);
  }
}
```
H4 已把 `80` 改为动态 `maxPages`,本项与 H4 同文件一起落地。

**⑤ 影响范围**
- 改:`backtest/okx.mjs`。
- **不该动**:调用方(对外签名不变)。

**⑥ 验证方法**
- 正常路径回归:H4 的下载验证命令仍通过。
- 故障注入(**推测**,手动):临时把 URL 改错一个字符,确认会重试 4 次后才抛错(日志可见间隔),而非立即失败。

**⑦ 依赖**
与 H4 同步落地(同文件)。

---

### Step 2 — 数据清洗

#### M1. 清洗规则会误删真实极端行情

**② 问题**
`backtest/clean.mjs:49-50` 定义 `highLowRatio`、`openCloseRatio`,`:64-65` 要求二者 `<= 5`,否则 `isValidCandle` 返回 false,在 `:83-86` 被推入 `invalidRows` 静默丢弃。品种列表含 PEPE/BONK/WIF/SHIB/FLOKI/ORDI/SATS 等(`run-multi-symbol-1d.mjs:57-63`),其早期日线单日 5x 完全可能,会被当无效删除;删除后 `:95-104` 还把它记成 missing gap。

**③ 影响**
真实暴涨暴跌日被删 → ATR%/振幅/分位全部被压低;meme/新币子集尤甚;与 H5 不降权叠加放大失真。删除还制造 gap,进一步污染连续性判断。

**④ 修复方案**
极端比值**不删,改标记保留**,只删真正非法 K 线:
```js
function isStructurallyValid(candle) {
  return finite(candle.openTime) &&
    finite(candle.open) && finite(candle.high) &&
    finite(candle.low) && finite(candle.close) && finite(candle.volume) &&
    candle.open > 0 && candle.high > 0 && candle.low > 0 && candle.close > 0 &&
    candle.high >= Math.max(candle.open, candle.close) &&
    candle.low <= Math.min(candle.open, candle.close);
}
function isExtreme(candle) {
  const hl = candle.low > 0 ? candle.high / candle.low : Infinity;
  const oc = Math.max(candle.open, candle.close) / Math.min(candle.open, candle.close);
  return hl > 5 || oc > 5; // 仅标记,不丢弃
}
```
保留极端 K 线进入 `candles`,但在该 candle 上打 `extremeFlag: true`,并在 metadata 统计 `extremeRows` 计数(替代原 `invalidRows` 里这部分)。`invalidRows` 只保留结构非法的。

**⑤ 影响范围**
- 改:`backtest/clean.mjs`(`isValidCandle` 拆分、`cleanOkxRaw` 统计字段)。
- **不该动**:`candlesToCsvRows`(列结构尽量保持;如需加 `extremeFlag` 列需同步 `app.js`/读取方——**推测**当前 CSV 无人按列名强校验,但仍建议本步先只加进 JSON 的 metadata,不改 CSV 列)。

**⑥ 验证方法**
- 对一个 meme 品种(如 `npm run clean -- --instrument PEPE-USDT --bar 1D`)对比修复前后 `cleanRows`:修复后应**增多**,`metadata.missingBars` 应减少。
- 抽查被原规则删掉的某日期,确认现在保留且 `extremeFlag` 为真。
- BTC-USDT 1D 回归:`cleanRows` 基本不变(BTC 极少触发 5x)。

**⑦ 依赖**
在 H4 之后(先有完整下载再谈清洗口径)。是 Step 3 及之后所有统计的前提。

---

### Step 3 — 指标口径

#### L1. ATR% 分母用 open 而非 close

**② 问题**
`backtest/indicators.mjs:151` 和 `:168` 计算 `atrPct = safeDivide(atr, candle.open) * 100`,用开盘价作分母。乖离率(`:287,292`)用 baseline,惯例 ATR% 多用 close,口径不一致。

**③ 影响**
轻微口径偏差;但 `atrPct` 是 `atrPercentile`、`state-features`、SOM、灯号的上游,任何改动都会平移整条链。**这是一个口径选择,不是明显 bug**——若决定改,必须趁早(本步),改后全链需重算。

**④ 修复方案**
二选一并在 spec 记录决定:
- 方案①(推荐,惯例):分母改 `candle.close`。
- 方案②(维持现状):不改,仅在文档/字段注释标明"ATR%=ATR/open"口径。
> 若选①:`safeDivide(atrValues[index], candle.close) * 100`,同处 fibAtr 的 `bundle.atrPctValues`(`:151`)一并改。

**⑤ 影响范围**
- 改(若选①):`backtest/indicators.mjs`(`buildAtrBundle`、`buildIndicatorSnapshots` 中 atrPct 计算)。
- 连带:所有已生成的 `reports/*` 需重算(非代码,是数据产物)。
- **不该动**:`deviationInAtr`、乖离率计算(它们用 baseline,本就独立)。

**⑥ 验证方法**
- 单点手算:取某日 ATR 与 close,核对 `atrPct` 输出。
- 全量回归:重跑 `npm run weather:router -- --instrument BTC-USDT` 不报错,`atrPct`/`atrPercentile` 数值平移合理(无 NaN/0 异常)。

**⑦ 依赖**
M1 之后(干净数据);**必须先于** Step 6/7/8 的任何重算,因为它平移特征值。

---

#### L2. "剩余动能"语义/命名反向

**② 问题**
`backtest/indicators.mjs:219` `remainingMomentumAtr = volatilityMultiple - 1`(=振幅/ATR − 1)。振幅已超 ATR 表示动能**已释放**,却被命名"剩余动能",`market-weather-router.mjs:115` 进一步标"动能已超ATR / 剩余动能为正"。前端 `app.js:219,370` 显示"剩余动能/余动能转正"。

**③ 影响**
纯语义误导,内部计算一致、无数值错误。读者可能把"剩余动能为正"误解为"还有上冲空间",实际相反。

**④ 修复方案**
不改数值,只改命名与展示文案,使语义自洽(二选一):
- 改名为 `rangeExcessAtr`/`波动超额`,文案改为"当根振幅已超 ATR x 倍";或
- 保留字段名,但前端/状态文案明确"已释放动能"语义。
> 建议与 L1 同批改 `indicators.mjs`,避免二次触碰。

**⑤ 影响范围**
- 改:`backtest/indicators.mjs`(字段名,若改名)、`market-weather-router.mjs`(`classifyEnergy` 文案)、`app.js`(展示文案)。
- **不该动**:任何依赖该数值的阈值逻辑(数值不变)。

**⑥ 验证方法**
- 文案 review;若改字段名,全仓库 `grep remainingMomentumAtr` 确认引用全部同步(`state-features.mjs:9,26-29`、`feature-factory`、前端等)。

**⑦ 依赖**
与 L1 同步(同文件)。若改字段名,波及面较广,建议放在 L1 之后单独验证。

---

### Step 4 — 聚合

#### L4. 单根 4H 缺失即丢整根 8H

**② 问题**
`scripts/run-multi-symbol-1d.mjs:225-259` `aggregateCandles`:`:241` 要求桶内恰好 `groupSize`(2)根,`:243-245` 要求两根严格连续,否则整桶 `return []` 丢弃。任何一根 4H 缺失/被删,对应 8H 整根消失。

**③ 影响**
与 M1(删极端)叠加会放大 8H 空洞;8H 完整性强依赖 4H 完整性。聚合边界(epoch 对齐 00/08/16 UTC)本身正确。

**④ 修复方案**
M1 完成后,4H 删除已大幅减少,本项可降级为"容忍单边缺失的可选聚合":
- 保守做法(推荐):维持"必须 2 根"策略,但在被丢弃时累加 `droppedBuckets` 计数进 metadata,供 H5 评估 8H 质量。
- 激进做法(可选):允许只有 1 根时也生成 8H(用单根 OHLC),并标 `partial: true`——**需谨慎**,会引入半根 8H,默认不采用。

**⑤ 影响范围**
- 改:`scripts/run-multi-symbol-1d.mjs`(`aggregateCandles`、`deriveCleanPayload` metadata)。
- **不该动**:`barToMs`、聚合边界(已正确)。

**⑥ 验证方法**
- 跑 `npm run multi:periods -- --symbols BTC-USDT --skip-download`(**推测**需先有 4H raw),检查 8H `cleanRows` 与 `droppedBuckets`;与修复前对比 8H 根数应不减少。

**⑦ 依赖**
M1 之后(干净 4H 是前提)。

---

### Step 5 — 历史质量与降权

#### H5. 短历史品种不降权,periodWeight 未被消费

**② 问题**
`scripts/run-multi-symbol-1d.mjs:184-196` `historyQuality`:仅 `1W` 分级降权(`:189-195`),**1D/4H/8H 只要 `cleanRows>=233` 即 `periodWeight:1`**。且 `periodWeight` 写入 summary 后,`writeCombinedSummary`/`writeBarSummary` 只罗列、不加权,前端也不读——是纯展示字段。

**③ 影响**
上市一年的薄历史山寨(warmup 后仅约 132 快照)与 BTC 10 年等权混在汇总;灯号噪声大却不降权。

**④ 修复方案**
- 对所有周期按"warmup 后有效快照数 + H4 截断标记"分级:
  ```js
  function historyQuality(config, cleanRows, hasCurrent, meta) {
    if (!hasCurrent || cleanRows < config.indicator.maPeriod) {
      return { dataStatus: "insufficient_history", historyQuality: "insufficient", periodWeight: 0 };
    }
    const effective = cleanRows - config.indicator.maPeriod;        // warmup 后样本
    let weight = Math.min(1, effective / 500);                       // 推测阈值,可调
    if (meta?.truncated) weight *= 0.7;                              // H4 截断降权
    if (config.bar === "1W") weight = Math.min(weight, weeklyCap(cleanRows));
    const quality = weight >= 1 ? "full_weight" : weight >= 0.5 ? "half_weight" : "weak_display_only";
    return { dataStatus: "ok", historyQuality: quality, periodWeight: round(weight, 2) };
  }
  ```
- **让 periodWeight 真正生效**:在 `writeCombinedSummary` 的任何排序/汇总统计、以及前端总览(Step 10)里,按 `periodWeight` 加权或在权重 < 阈值时降级显示。

**⑤ 影响范围**
- 改:`scripts/run-multi-symbol-1d.mjs`(`historyQuality`、汇总写出)。
- 连带(Step 10):前端读取 `periodWeight/dataStatus`。
- **不该动**:单品种灯号本身(降权是汇总层概念,不改单品种 gate)。

**⑥ 验证方法**
- 跑多品种,检查薄历史品种(如新上市币)`periodWeight<1`、`historyQuality` 非 full;BTC 1D `periodWeight=1`。
- 断言 4H/8H 截断品种(H4 `truncated:true`)权重被打折。

**⑦ 依赖**
H4(需 `truncated` 标记)、M1(需干净 `cleanRows`)。被 Step 10 消费。

---

### Step 6 — 偏离研究

#### M6. 指标分桶用全样本分位(离线口径混入)

**② 问题**
`backtest/deviation-study.mjs:221-245` `rankRowsByMetric` 对每个历史行的 `rankPct/bucket` 用**全体 selected** 排名(`:231` `index/(values.length-1)`),历史行的"极高/极低"标签知道了未来分布。该结果喂 `metricSummaryRows`/`contrastMetricRows`。
注:进 gate 的 state 分类 `classifyDeviation`(`:76-102`)用的是 prefix 因果的 `positionPct`,本身干净;故本项严重度为中。

**③ 影响**
指标分桶统计是离线全样本口径,不能当前推;若被误用为实时判断会引入前视偏差。是"离线研究口径与实盘前推口径混用"的典型。

**④ 修复方案**
分桶改用扩展窗口的因果分位(只用 ≤t 数据),或明确隔离:
- 因果化:把 `rankPct` 改为 `prefixPercentile`(已有于 `indicators.mjs:110-147`,可抽公用)。
- 或最小改动:在产物 metadata 标注 `metricBuckets: "offline_full_sample"`,并确保灯号链不读取这些字段(经核 gate 只读 state 分类,符合)。

**⑤ 影响范围**
- 改:`backtest/deviation-study.mjs`(`rankRowsByMetric` 或其消费标注)。
- **不该动**:`classifyDeviation`、`currentRows` 的 state 路径(已因果)。

**⑥ 验证方法**
- 若因果化:对比某历史中段行的 bucket,修复后不应受其之后数据影响(可截断数据集到该行再跑,bucket 不变)。
- 确认 `market-weather-router` gate 输出不因本改动变化(因 gate 不读 metric 桶)。

**⑦ 依赖**
Step 3 之后。建议在 Step 7 灯号消费偏离概率之前完成。

---

### Step 7 — 主灯号改造(B 方案核心)

> 7a → 7b → 7c 严格有序。7a 是 7b 的结构前提。

#### 7a / L6. 打分引擎归一(统一三套打分)

**② 问题**
仓库存在 3 套打分:
- `routeStrategies`(`strategy-router.mjs:38-211`)——规范引擎,8 方向+5 聚合,被回测/校准/feature-factory 使用。
- `scoreStrategies`(`market-weather-router.mjs:364-437`)——主灯号专用,5 family,**另一套系数**。
- `scoreStrategyFit`(`feature-factory.mjs:209-271`)——**死代码,全仓库无人调用**(经 grep 确认)。

**③ 影响**
主灯号的当前分数口径与校准器建桶口径不一致,直接接校准器会**查错桶**;三套并存长期漂移、难维护。

**④ 修复方案**
以 `routeStrategies` 为唯一标准:
1. 删除死代码 `scoreStrategyFit`(`feature-factory.mjs:209-271`)。
2. 主灯号弃用 `scoreStrategies`,改用 `routeStrategies` 产出当前分数:
   ```js
   import { routeStrategies } from "./strategy-router.mjs";
   import { buildWeatherLabels } from "./feature-factory.mjs";
   // latest 快照:
   const labels = buildWeatherLabels(latest, config);
   const routeResult = routeStrategies(latest, labels);   // scores 含 13 键
   ```
3. 统一命名:主灯号原 `trend` 对齐到聚合键 `trendFollowing`(或全局统一为 `trend`,二选一并贯穿 `router-calibrator.mjs:225` 的过滤名单)。
4. 输出 schema 尽量保持:`strategyScores` 仍为 `{key,label,score}[]`,`current.topWeatherRoute/topWeatherScore/weatherSummary` 字段名不变,只换数据来源——以免波及 `run-multi-symbol-1d.mjs:178-182,347` 与 `app.js:109,199,395`。

**⑤ 影响范围**
- 改:`backtest/market-weather-router.mjs`(删 `scoreStrategies`,改 `buildMarketWeatherRouter`)、`backtest/feature-factory.mjs`(删死代码)。
- 可能微调:`backtest/router-calibrator.mjs:225` 过滤名单命名对齐。
- **不该动**:`strategy-router.mjs` 系数(规范引擎保持稳定)、`strategy-router-backtest.mjs` 的 `routeOutcome`(成功判定不能在此步同改)。

**⑥ 验证方法**
- `grep scoreStrategyFit` 返回空(死代码已除)。
- `grep scoreStrategies` 仅余历史无引用或已删。
- 跑 `npm run weather:router -- --instrument BTC-USDT`,输出结构(`strategyScores`、`current` 字段)与改前一致,前端能正常渲染。

**⑦ 依赖**
Step 6 之后;是 7b 的前置。

---

#### 7b / H2. 接入 router-calibrator

**② 问题**
`backtest/market-weather-router.mjs` 从不 import 校准器;主灯号 `gateFromScores`(`:439-456`)用 `topActiveScore/waitScore` 魔数阈值。`runStrategyRouterBacktest` 被 market-state/validation/calibrator 用,唯独主灯号没用。

**③ 影响**
唯一带样本置信度与基线对比的逻辑被晾置;上线的是裸魔数 gate,红黄绿无历史校准依据。

**④ 修复方案**
1. `buildMarketWeatherRouter` 调用校准:
   ```js
   import { runRouterCalibration } from "./router-calibrator.mjs";
   const calibration = runRouterCalibration(cleanPayload, config);
   const signals = calibration.metadata.currentSignals; // 各方向路由的 light/calibrationScore/sampleConfidencePct
   ```
2. 新增"N 路由灯 → 单主灯"折叠规则(**新逻辑,需设计**,推测 30-50 行),例如:
   ```js
   // 推测示意:取各 family 最佳方向路由的 light,按绿/黄/红计权折叠
   function gateFromCalibration(signals) {
     const greens = signals.filter(s => s.light === "绿灯");
     const reds   = signals.filter(s => s.light === "红灯");
     if (greens.some(s => s.signalType.includes("方向")) ) return "绿";
     if (greens.length && !reds.length) return "黄偏绿";
     if (reds.length >= signals.length - 1) return "红";
     // ... 含 wait/防守路由的特殊处理
     return "黄";
   }
   ```
   折叠规则要保留原有"黄偏红/黄偏绿"粒度,映射到前端 `gateClass`(`app.js:37-43`)已识别的字样(红/黄/绿/黄偏)。
3. 替换 `gateFromScores` 调用为 `gateFromCalibration`;`topWeatherRoute` 取校准最佳路由。

**⑤ 影响范围**
- 改:`backtest/market-weather-router.mjs`(`buildMarketWeatherRouter`、新增折叠函数、弃用 `gateFromScores`)。
- 性能:每品种×周期多跑一次 `runStrategyRouterBacktest`;**建议复用** 已 build 的 snapshots,避免 `strategy-router-backtest.mjs:238` 与 `market-weather-router.mjs:528` 重复 build(**推测**需给 backtest 加可选 snapshots 入参)。
- **不该动**:`router-calibrator.mjs` 内部算法(本步只消费,不改其逻辑)、`routeOutcome` 判定。

**⑥ 验证方法**
- 跑 BTC-USDT 1D,确认 `current.gate` 现在由校准结果驱动:人为构造/选取一个历史上 trend 路由 occ 充足且 lift 高的当前态,gate 应偏绿;occ<30 的态不应给绿。
- 对比改前后同日 gate,记录差异并人工核对方向是否更合理。
- 全 58 品种跑通,无异常抛错。

**⑦ 依赖**
7a(引擎统一)必须先完成;数据层 Step 1-2 必须先完成(否则校准建立在被截断/误删的历史上)。

---

#### 7c / H3. 样本置信度并入 gate

**② 问题**
`gateFromScores`(`:439-456`)只看 state 与分数,**不读** occurrences/confidence;`scoreStrategies` 旧逻辑里 `middleCloserEdge`(`:387,402-408`)无样本下限直接加权;`deviation-rules.mjs:194-246` `finalWeather` 算了 `confidenceLabel`(`:243`)却只展示、gate 分支(`:224-233`)不用。`confidenceLabel(samples<120)→"样本偏少"`(`:14-20`)形同虚设。

**③ 影响**
小样本/新品种的偶然概率可直接翻转主灯号。

**④ 修复方案**
在 7b 的折叠规则里把样本置信度作为硬闸:
```js
// 任何路由想贡献"绿灯",必须满足样本门槛
const MIN_OCC = 30, MIN_CONF = 40; // 推测阈值,与校准器 sampleConfidence 口径一致
function effectiveLight(signal) {
  if (signal.occurrences < MIN_OCC || signal.sampleConfidencePct < MIN_CONF) {
    return signal.light === "绿灯" ? "黄灯" : signal.light; // 低置信不得给绿
  }
  return signal.light;
}
```
- 偏离规则 `finalWeather` 同样:`gate` 分支前先看 `confidenceLabel`,"样本偏少"时不得升级为更激进结论。
- 校准器自身已有 `occ<30` 闸门(`router-calibrator.mjs:123-126,155-161`),本步是在**主灯折叠层再加一道**,确保低置信不改色。

**⑤ 影响范围**
- 改:`backtest/market-weather-router.mjs`(折叠函数)、`backtest/deviation-rules.mjs`(`finalWeather` gate 分支引入 confidence)。
- **不该动**:`confidenceLabel` 阈值定义(复用现有)。

**⑥ 验证方法**
- 选一个 occ<30 的当前态(如冷门小周期),确认其即使分数高也拿不到绿灯。
- 对比改前后,统计 58 品种里"绿灯"数量应下降(小样本绿灯被降级),且降级的都能在数据里看到 occ/置信不足。

**⑦ 依赖**
7b 之后(折叠规则已就位)。

---

### Step 8 — 训练层

#### M2. SOM 全样本 z 归一 + 样本内状态-策略灯

**② 问题**
- `backtest/state-features.mjs:87-108` z-score 用**全样本** mean/std 归一(`:87` stats 对全体行算,`:103-108` 归一每行),历史某天 z 值"知道"未来分布 → 训练层前视偏差。
- `backtest/market-state.mjs:325-326,170-219` 状态的 `strategyProfile` 用 `runStrategyRouterBacktest` 的**样本内**未来收益算成功率,`routeLight`(`:135-168`)直接打绿/红灯,当前状态展示得像可前推。
- 决策树(`:362-372`)标签即 SOM `stateId`(特征的确定性函数),**树只是蒸馏 SOM 分区**,非预测。

**③ 影响**
"状态识别"作为描述性聚类成立;但"可前推/有预测力"不成立,灯号有样本内乐观偏差,易被误读为预测结论。

**④ 修复方案**
- z 归一改扩展窗口因果化(只用 ≤t 数据),或明确该模型只用于**当前态描述**、不做历史回放预测。
- 状态-策略胜率走 train/validate 切分(复用 `decision-tree-validation.mjs:127-137` 的 `inDateRange` 范式)。
- 在产物与前端明确标注:"状态画像基于历史样本内统计,非样本外预测"。

**⑤ 影响范围**
- 改:`backtest/state-features.mjs`(归一)、`backtest/market-state.mjs`(胜率切分/标注)。
- **不该动**:`decision-tree-validation.mjs`(其切分已正确,作为范式参考)、灯号层(M2 与 gate 解耦)。

**⑥ 验证方法**
- 截断数据到某中段日期再训练,确认该日之前行的 z 值/状态不随之后数据变化。
- 状态胜率报告出现 train/validate 两段,validate 段胜率应低于样本内(符合预期则说明切分生效)。

**⑦ 依赖**
Step 3(特征值定稿)之后。与 Step 7 解耦,可并行。

---

### Step 9 — 前端健壮性

#### M4. maRule kindKey "ma" 永不匹配 "ma233"

**② 问题**
`app.js:142-144` 用 `row.kindKey === "ma"` 查找,但实际 kindKey 是 `"ma233"`(`deviation-study.mjs:24`)。`maRule` 恒为 `undefined`,"大周期过滤"卡片回归/远离概率永远走 fallback(`app.js:175`),deviation 报告的 ma 规则从不被采用。静默退化,不报错。

**③ 影响**
前端大周期卡片展示的是降级数据而非偏离规则的真实概率,误导但不崩。

**④ 修复方案**
```js
const maRule = (deviations?.currentRuleRows ?? []).find(
  (row) => row.kindKey === "ma233" && Number(row.horizon) === 10,
);
```

**⑤ 影响范围**
- 改:`app.js`(`renderComponentGrid`)。
- **不该动**:后端 kindKey(`ma233` 是正确值,不要为迁就前端去改后端)。

**⑥ 验证方法**
- 打开页面,"大周期过滤"卡片"远离 X%"应与 `*_deviation_rules.json` 里 `kindKey:"ma233", horizon:10` 的 `continueAwayProbabilityPct` 一致(改前会等于 fallback 的 `current.maTenDayContinueAwayPct`)。

**⑦ 依赖**
无(独立、可提前)。归入前端步统一回归。

---

#### M5. current=null 时崩成通用"加载失败"

**② 问题**
`app.js:390` 直接 `weather.current.date`,`renderOverview:104` 直接读 `current.gate`。当品种历史不足时 `buildMarketWeatherRouter` 返回 `current:null`(`market-weather-router.mjs:538`),前端抛 TypeError 被 `:411` 的 `.catch` 吞成"加载失败"。`dataStatus:"insufficient_history"` 无 UI 分支。当前因写死 BTC 不触发,泛化到多品种会崩。

**③ 影响**
多品种接入(Step 10)后,任一薄历史品种导致整页"加载失败"。

**④ 修复方案**
```js
async function renderDashboard() {
  const [weather, ...] = await Promise.all([...]);
  if (!weather?.current) {
    renderInsufficient(weather?.metadata);   // 渲染"样本不足/灰灯"占位
    return;
  }
  // ... 原逻辑
}
```
新增 `renderInsufficient` 展示灰灯 + "历史不足,暂不出灯"。

**⑤ 影响范围**
- 改:`app.js`(`renderDashboard` 守卫 + 新增占位渲染)。
- **不该动**:后端返回结构(null 是合法的"数据不足"信号)。

**⑥ 验证方法**
- 临时把 `PATHS.weather` 指向一个 `current:null` 的产物(或薄历史品种),确认页面显示灰灯占位而非"加载失败"。
- BTC 正常品种仍正常渲染。

**⑦ 依赖**
无;**必须先于 Step 10**(多品种会暴露此问题)。

---

### Step 10 — 前端接入多品种/多周期汇总

#### M3. app.js 硬编码 BTC 1D;多周期汇总未接入

**② 问题**
`app.js:1-6` 写死四个 `BTC_USDT_1D_*` 路径,`renderDashboard:382-387` 只拉这四个。`multi_period_market_weather_current.json` / `multi_<bar>_*.csv` 等汇总产物前端完全不用,无品种/周期选择器或 URL 参数。

**③ 影响**
58 品种 × 4 周期的成果只能看 BTC 1D 一个;违背"多品种天气雷达"目标。

**④ 修复方案**
- 路径改为按参数拼接:
  ```js
  const params = new URLSearchParams(location.search);
  const symbol = (params.get("symbol") || "BTC-USDT").replaceAll("-", "_");
  const bar = params.get("bar") || "1D";
  const PATHS = {
    weather: `./reports/${symbol}_${bar}_market_weather_router.json`,
    features: `./reports/${symbol}_${bar}_feature_factory.json`,
    deviations: `./reports/${symbol}_${bar}_deviation_rules.json`,
    candles: `./data/clean/${symbol}_${bar}_clean.json`,
  };
  ```
- 新增总览视图读取 `reports/multi_period_market_weather_current.json`,列出各品种×周期的 `gate / topWeatherRoute / periodWeight / dataStatus`,并按 `periodWeight`(Step 5)排序/降级展示;点击进入单品种详情。

**⑤ 影响范围**
- 改:`app.js`、`index.html`(新增选择器/总览容器)、可能 `styles.css`。
- **不该动**:后端产物结构(已具备 multi_period 汇总)。

**⑥ 验证方法**
- `?symbol=ETH-USDT&bar=4H` 能正确加载对应产物。
- 总览表行数 = 跑过的品种×周期数;薄历史品种显示降权/灰灯(依赖 Step 5)。

**⑦ 依赖**
Step 5(汇总含 periodWeight/dataStatus)、Step 9(空数据不崩)。

---

### Step 11 — 前端展示

#### L5. 概率英雄卡缺样本/置信语境

**② 问题**
`app.js:146-183`(`renderComponentGrid`)与 `:363-378`(`renderNotes`)把"回归 X%""降波 X%"当确定结论展示,未带样本数/置信。下方表格 `renderDeviationTable`(`:325-361`)已有"置信"列,英雄卡却没有。

**③ 影响**
概率被误读成确定性结论;尤其小样本概率显示得和厚样本一样"确定"。

**④ 修复方案**
- 英雄卡与结论文案补样本/置信:如"回归 62%(样本 180,置信:中强)";样本不足时弱化或标灰。
- 可复用后端已给的 `occurrences`/`confidence` 字段(component/deviation 行均有)。

**⑤ 影响范围**
- 改:`app.js`(`renderComponentGrid`、`renderNotes`)、可能 `styles.css`。
- **不该动**:后端概率计算。

**⑥ 验证方法**
- 页面英雄卡出现样本/置信标注;对一个小样本态,显示明显的"样本偏少"弱化样式。

**⑦ 依赖**
Step 10(新汇总视图就位)之后收尾。

---

## 4. 附录

### 4.1 已核实"无需修复"的部分(防止误改)
- **分位数无未来函数**:`indicators.mjs:110-147`(`prefixPercentile`,Fenwick 前缀计数)与 `:91-108`(`prefixExtrema`)严格因果,t 时刻只用 ≤t 数据。**不要"优化"成全样本。**
- **ATR/振幅、中值乖离、233MA 乖离、3/8/13/21 ATR 计算正确**:Wilder ATR(`:54-68`)、`deviationInAtr`(`:70-75`)、`fibAtrComparisons`(`:239-245`)口径自洽。
- **8H 聚合边界正确**:`run-multi-symbol-1d.mjs:225-259` epoch 对齐 00/08/16 UTC,4H 开盘恒落在 4 的倍数小时,聚合无错位。L4 只是健壮性,不是边界 bug。
- **决策树前推验证切分正确**:`decision-tree-validation.mjs:127-237` 用 `inDateRange` 真实切分,且用原始因果特征 `row.values`,无切分泄漏。**前视偏差只在 SOM 线(M2),不在验证树。**
- **校准器无"当前 bar 未来函数"**:`strategy-router-backtest.mjs:37-42` `scoreBucket` 用固定阈值非分位,当前 bar 因无未来被排除(`:259`)。其局限是"样本内非 walk-forward",不是泄漏。

### 4.2 跨步骤回归清单
改完整链或灯号层后,跑以下命令并比对产物:
```powershell
npm run download -- --instrument BTC-USDT --bar 4H --days 3650   # H4:rowCount≫8000
npm run clean    -- --instrument PEPE-USDT --bar 1D              # M1:cleanRows 增、missingBars 减
npm run weather:router -- --instrument BTC-USDT --days 3650      # 7a/7b/7c:gate 由校准驱动
npm run multi:periods  -- --symbols BTC-USDT,ETH-USDT           # H5/L4:periodWeight、8H 根数
npm run serve                                                   # M3/M4/M5/L5:前端 ?symbol=&bar=
```
重点对比:`reports/BTC_USDT_1D_market_weather_router.json` 的 `current.gate` 改前/改后差异;`multi_period_market_weather_current.csv` 的 `periodWeight` 列是否非平凡。

### 4.3 标注为"推测"的条目汇总(执行时须复核)
- H4:OKX 单页上限 100、动态 `maxPages` 公式与冗余系数。
- H5:`effective/500` 权重阈值、`*0.7` 截断折扣。
- 7b:N 路由灯→主灯的折叠规则(全新逻辑,需设计);复用 snapshots 需给 `runStrategyRouterBacktest` 加入参。
- 7c:`MIN_OCC=30 / MIN_CONF=40` 阈值。
- L4 激进做法、M2 因果归一的具体窗口长度。
- 回归清单命令中 `--skip-download` 等本地前置条件。
