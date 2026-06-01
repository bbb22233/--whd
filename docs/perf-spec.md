# 性能优化规格:复用 snapshots(B)

> 对应审计/施工序列里的"性能项":`buildMarketWeatherRouter` 接入校准器后重复构建一次指标快照。
> 本文件是**只读施工方案**,执行由本地完成。**纯性能优化,不得改变任何算法结果(时间戳除外)。**

代码基线:`main @ 2b0aac5`(含 Step 1–7 全部修复)。

---

## 1. 目标
`buildMarketWeatherRouter` 每次构建一次 `snapshots`,接入校准器后又在内部**重复构建一次**。
目标:让校准链复用已构建的 `snapshots`,**输出逐字段不变**,只去掉这一次冗余 `buildIndicatorSnapshots`。

## 2. 重复点(真实行号 @ `main 2b0aac5`)
```
market-weather-router.mjs:676   snapshots = buildIndicatorSnapshots(cleanPayload.candles, config)   ← 第 1 次
market-weather-router.mjs:681   runDeviationStudyFromSnapshots(..., snapshots)                     ← 已复用(好)
market-weather-router.mjs:684   runRouterCalibration(cleanPayload, config)                         ← 没传 snapshots
   └─ router-calibrator.mjs:248  runStrategyRouterBacktest(cleanPayload, config)
        └─ strategy-router-backtest.mjs:238  buildIndicatorSnapshots(...)                          ← 第 2 次(冗余)
```
每个"品种×周期"多算一次 `buildIndicatorSnapshots`;58×4 ≈ 多 232 次。

## 3. 改法(向后兼容的可选入参,3 处)
给两个函数加**可选第三参** `snapshots`,缺省则内部自建(行为不变):

```js
// strategy-router-backtest.mjs:237
export function runStrategyRouterBacktest(cleanPayload, config, snapshots) {
  const builtSnapshots = snapshots ?? buildIndicatorSnapshots(cleanPayload.candles, config);
  // 其余把原 snapshots 引用替换为 builtSnapshots,逻辑不动(含其内部的 inWindow 过滤)

// router-calibrator.mjs:247
export function runRouterCalibration(cleanPayload, config, snapshots) {
  const backtestResult = runStrategyRouterBacktest(cleanPayload, config, snapshots);

// market-weather-router.mjs:684 —— 把已建的 snapshots 透传进去
const calibration = latest ? runRouterCalibration(cleanPayload, config, snapshots) : null;
```

只有这 3 处,纯透传,不碰任何打分/分桶/灯号逻辑。

## 4. 影响范围
- **要改**:`strategy-router-backtest.mjs`、`router-calibrator.mjs`、`market-weather-router.mjs`(各几行)。
- **不该动**:`buildIndicatorSnapshots` 本体、`routeStrategies` / `routeOutcome` / 校准评分 / `gateFromCalibration` / `applyConfidenceGateToSignals` 等任何算法;`fix-spec.md` 附录 4.1 红线(Wilder ATR、prefixPercentile、prefixExtrema、8H 聚合边界、验证树切分)。
- **不该改变**:任何输出字段的值(时间戳除外)。

## 5. 兼容性核对(其他调用方为何不受影响)
两个函数现有调用方全部**不传第三参**,走 `?? 内部自建`,行为逐字节一致:
```
runStrategyRouterBacktest:
  market-state.mjs:325 · decision-tree-validation.mjs:417 · router-calibrator.mjs:248
  · decision-tree-suite.mjs:322 · scripts/backtest-strategy-router.mjs:17
runRouterCalibration:
  market-weather-router.mjs:684 (唯一传参方) · decision-journal.mjs:234 · scripts/calibrate-router.mjs:17
```
只有 `market-weather-router:684` 会传 snapshots,其余原样。

## 6. 自证"结果不变"(本地执行)
`buildIndicatorSnapshots(candles, config)` 是**纯确定性函数**,复用同一份 `cleanPayload`/`config` 下的 snapshots 必然得到相同下游。

```bash
# ① 改动前(干净的 2b0aac5)产基线
npm run weather:router -- --instrument BTC-USDT --bar 4H --days 3650
cp reports/BTC_USDT_4H_market_weather_router.json /tmp/before.json

# ② 应用 B 改动后再产一次
npm run weather:router -- --instrument BTC-USDT --bar 4H --days 3650
cp reports/BTC_USDT_4H_market_weather_router.json /tmp/after.json

# ③ 剔除易变时间戳后严格 diff(期望:完全一致)
jq 'del(.metadata.generatedAt)' /tmp/before.json > /tmp/b.json
jq 'del(.metadata.generatedAt)' /tmp/after.json  > /tmp/a.json
diff /tmp/b.json /tmp/a.json && echo "RESULT-UNCHANGED ✅"
```
- **期望**:`diff` 无输出 + 打印 `RESULT-UNCHANGED ✅`。重点核对 `current.gate`、`strategyScores`、`metadata.currentCalibrationSignals`、`deviationFinalWeather` 全等。
- 至少再挑 1 个**薄样本**品种 + 1 个 `1W` 周期各跑一遍,覆盖"有/无校准信号"两条路径。
- 可选加固:改动里临时 `console.assert(JSON.stringify(reused)===JSON.stringify(rebuilt))`,跑一次确认后删除。

## 7. 性能预期(诚实口径)
- 省掉的是**每品种×周期一次 `buildIndicatorSnapshots`**,**不是**总时长减半——校准器大头是 8 路由 × horizons × 全样本回测循环,那部分不变。
- 量化:`time node scripts/run-multi-symbol-1d.mjs --bars 4H` 前后对比 wall-clock;预期可测下降,幅度取决于指标构建占比,**不承诺固定百分比**。

## 8. 风险与边界(scope guard)
- **只做这一个重复**。不要顺手 dedup `buildFeatureFactory` / 独立 `runDeviationStudy` 各自的 snapshots——那是更大范围的流水线改造,不属于 B。
- 复用前提:传入 snapshots 必须来自**同一 `cleanPayload.candles` 和同一 `config`**(`market-weather-router:676` 正满足)。
- `runStrategyRouterBacktest` 内部会对 snapshots 再做 `inWindow` 过滤——传**全量** snapshots 即可(与现在内部自建后过滤完全一致),不要在外面先过滤再传。

## 9. 验收登记(本地填)
| 项 | 期望 | 实际 |
|---|---|---|
| BTC 4H diff | `RESULT-UNCHANGED ✅` | TODO |
| 薄样本品种 diff | 一致 | TODO |
| 1W 周期 diff | 一致 | TODO |
| `time multi --bars 4H` 前/后 | 后 < 前 | TODO |
| 其他 7 个调用方 | 行为不变 | TODO(可跑 calibrate-router / backtest:router 抽验) |
