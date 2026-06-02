# 前端健壮性规格:M4 + M5(Step 9)

> 对应 `docs/fix-spec.md` 的 Step 9。**只读施工方案**,执行由本地完成。只动 `app.js`(除非显式选择做灰屏占位样式)。
> 代码基线:`main @ a962ebc`(含 Step 1–7 + perf + M2)。

M3(多品种接入)、L5(概率语境)是后续步骤,不在本文件;但 **M5 是 M3 的前置**(多品种会大量触发 `current=null`)。

---

## M4 — `maRule` 永远匹配不上(kindKey 拼错)

**状态:⏳ 待做**

### 问题(行号 @ a962ebc)
`app.js:143`:
```js
const maRule = (deviations?.currentRuleRows ?? []).find(
  (row) => row.kindKey === "ma" && Number(row.horizon) === 10,
);
```
实际 kindKey 是 `"ma233"`(见 `backtest/deviation-study.mjs` 的 `studyDefs`)。`maRule` 恒为 `undefined`。

### 影响
"大周期过滤"卡片(`renderComponentGrid`)的"远离 %"永远走 fallback(`current.maTenDayContinueAwayPct`),deviation 规则里真正的 `ma233 / horizon=10` 概率从不被采用。静默退化、不报错。

### 修复方案
```js
(row) => row.kindKey === "ma233" && Number(row.horizon) === 10,
```

### 影响范围
- 改:`app.js`(仅 `renderComponentGrid` 这一行)。
- **不该动**:后端 `kindKey`——`"ma233"` 是正确值,不要为迁就前端把后端改成 `"ma"`。

### 验证(本地)
打开页面,"大周期过滤"卡片"远离 X%" 应等于 `reports/<symbol>_<bar>_deviation_rules.json` 里 `kindKey:"ma233", horizon:10` 的 `continueAwayProbabilityPct`;修复前等于 fallback 的 `current.maTenDayContinueAwayPct`。两者不同即证明修对了。

### 依赖
无,独立,可单独先做。

---

## M5 — `current=null` 时整页崩成"加载失败"

**状态:⏳ 待做**

### 问题(行号 @ a962ebc)
- `app.js:390`:`getCurrentCandle(candles, weather.current.date)` 直接读 `weather.current.date`。
- `app.js:104/108/114`(`renderOverview`):直接读 `current.gate` 等。
- 品种历史不足时 `buildMarketWeatherRouter` 返回 `current: null` → `weather.current.date` 抛 TypeError → 被 `:404/:410` 的 `.catch` 吞成通用 `加载失败: ...`。
- `dataStatus:"insufficient_history"` 没有任何 UI 分支。

### 影响
当前因写死 BTC 1D 不触发;一旦 M3 接多品种,任一薄历史品种就让整页崩成"加载失败",而非优雅显示"样本不足"。

### 修复方案
`renderDashboard` 拿到数据后、渲染前加守卫;`current` 为空就渲染占位并 return:
```js
async function renderDashboard() {
  setText("#weatherSummary", "数据加载中...");
  const [weather, features, deviations, candles] = await Promise.all([...]);

  if (!weather || !weather.current) {
    renderInsufficient(weather?.metadata);   // 灰灯 + “历史不足,暂不出灯”
    return;
  }
  // ...原有渲染逻辑不变
}
```
`renderInsufficient` 复用**现有 DOM 节点**(零新增 HTML):
```js
function renderInsufficient(metadata) {
  setText("#instrument", metadata?.instrument ?? "--");
  setText("#bar", metadata?.bar ?? "--");
  setText("#gateText", "样本不足");
  const panel = $("#gatePanel");
  if (panel) panel.className = "gate-panel gate-neutral";
  setText("#weatherSummary", "历史数据不足,暂不输出灯号");
  setText("#actionBias", "等待历史补齐");
}
```

### 影响范围
- 改:`app.js`(`renderDashboard` 守卫 + 新增 `renderInsufficient`)。
- **默认只动 `app.js`**:`renderInsufficient` 复用现有节点(`#gateText/#gatePanel/#weatherSummary/#actionBias/#instrument/#bar`),不加新 HTML。
- **若要专门的"灰屏占位"样式** → 才需碰 `index.html`/`styles.css`;默认不碰,要做再单独说。
- **不该动**:后端返回结构(`current: null` 是合法的"数据不足"信号,不要为了不崩在后端造假 current)。

### 验证(本地)
- 把 `PATHS.weather` 临时指向一个 `current:null` 的产物(或薄历史品种的 router JSON),确认页面显示"样本不足"灰灯占位,而非"加载失败"。
- 正常品种(BTC 1D)仍正常渲染、无 console 报错。

### 依赖
无前置;**必须早于 M3**。

---

## 执行建议
- 两项都只动 `app.js`、低风险;M4 一行,M5 一个守卫 + 一个小函数。
- 提交粒度:可合成 `fix(M4,M5): frontend robustness`,或拆两个,随你。
- 完成后把本文件两个 `⏳ 待做` 改为 `✅ 完成`,并在 `verification-log.md` 补一条前端健全性记录。
