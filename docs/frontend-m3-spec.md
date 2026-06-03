# 前端多品种/多周期接入规格:M3(Step 10)

> 对应 `docs/fix-spec.md` 的 Step 10。**只读施工方案**,执行由本地完成。
> 代码基线:`main @ f8ad174`(含 Step 1–9 + Python 后端 + dashboard API)。
> 前置已满足:M5(`renderInsufficient` 守卫)已完成;后端 `/api/dashboard/current` 与 `/api/market/symbols|overview|rows` 已就绪。

L5(概率语境)是后续步骤,不在本文件。

---

## M3 — 详情页仍硬编码 BTC-USDT / 1D

**状态:✅ 完成**

### 问题(行号 @ f8ad174)
`app.js:2-4`:
```js
const DEFAULT_INSTRUMENT = "BTC-USDT";
const DEFAULT_BAR = "1D";
const REPORT_PREFIX = `${DEFAULT_INSTRUMENT.replace("-", "_")}_${DEFAULT_BAR}`;
```
- `PATHS`(`:11-20`)的 dashboard / weather / features / deviations / candles **全部由这两个常量派生**,既包括 API 主路也包括静态 fallback。
- `index.html` 只有展示用的 `#instrument`/`#bar` span,**没有任何选择器**。
- 结果:后端 dashboard API 与 `/api/market/*` 已支持任意品种×周期,但**详情页只能看 BTC-USDT/1D**。这就是原审计 M3("app.js 硬编码 BTC 1D")在前端的残留。

### 影响
58 品种 × 4 周期的成果在详情页看不到;"多品种天气雷达"目标未达成。注意这是纯前端缺口——**后端无需改动**。

### 修复方案

**① 用 URL 参数驱动,常量改派生**
```js
const params = new URLSearchParams(location.search);
let instrument = normalizeInstrument(params.get("instrument")) || "BTC-USDT";
let bar = (params.get("bar") || "1D").toUpperCase();
```
把 `PATHS` 从常量对象改成函数,按当前 instrument/bar 重建——**主路和 fallback 都要重建**(关键,见下方坑):
```js
function buildPaths(instrument, bar) {
  const prefix = `${instrument.replace("-", "_")}_${bar}`;
  return {
    dashboard: `${API_BASE}/api/dashboard/current?instrument=${instrument}&bar=${bar}`,
    weather: apiReport(`${prefix}_market_weather_router.json`, `./reports/${prefix}_market_weather_router.json`),
    features: apiReport(`${prefix}_feature_factory.json`, `./reports/${prefix}_feature_factory.json`),
    deviations: apiReport(`${prefix}_deviation_rules.json`, `./reports/${prefix}_deviation_rules.json`),
    candles: { primary: `${API_BASE}/api/candles/${instrument}/${bar}`, fallback: `./data/clean/${prefix}_clean.json` },
  };
}
```
`fetchDashboardData` / `fetchLegacyDashboardData` 改为接收 `paths` 参数(或读模块级 `let PATHS = buildPaths(instrument, bar)`)。

**② 加选择器(index.html)**
在 topbar 放两个下拉(复用现有 `#instrument`/`#bar` 区域或新增):
```html
<select id="symbolSelect"></select>
<select id="barSelect">
  <option value="1D">1D</option><option value="4H">4H</option>
  <option value="8H">8H</option><option value="1W">1W</option>
</select>
```

**③ 填充与联动(app.js)**
- 品种列表从 `GET /api/market/symbols`(返回 `{count, symbols:[...]}`)填充;失败则回退到内置默认列表或隐藏品种选择器(只保留 URL 参数行为)。
- 选择变化时:更新 URL(`history.pushState({}, "", \`?instrument=${instrument}&bar=${bar}\`)`)→ 重建 PATHS → 重新 `renderDashboard()`。
- 初始化时把两个下拉的选中值同步成当前 instrument/bar。

### 影响范围
- 改:`app.js`(参数解析 + `buildPaths` + 选择器填充/联动)、`index.html`(两个 `<select>`)、可能 `styles.css`(下拉样式)。
- **后端不动**:dashboard API + `/api/market/symbols` 已满足。
- **不该动 / 不该破坏**:
  - M4(`kindKey === "ma233"`)、M5(`renderInsufficient` 守卫)逻辑保持。
  - dashboard API → 静态文件的 fallback 链保持。
  - 报告生成、`reports/` 结构、UI 视觉布局不改(与 api-dashboard-spec 一致)。

### ⚠️ 关键坑(务必照顾)
- **静态 fallback 也必须按所选 instrument/bar 重建**。若只参数化了 API 主路、fallback 仍用 BTC 前缀,则"API 挂掉 + 选了非 BTC"会**静默显示成 BTC** 的数据——比报错更危险。`buildPaths` 已把 fallback 一并重建,落地时不要漏。
- **非法/薄历史品种**:选了一个 `current=null` 的品种,必须走 M5 的 `renderInsufficient`(灰灯占位),不能崩。
- **品种名归一**:URL 传入的 instrument 要过一遍归一(`BTC_USDT`/`BTCUSDT` → `BTC-USDT`),与后端 `normalize_instrument` 口径一致,避免 404。

### 验证方法(本地)
- `?instrument=ETH-USDT&bar=4H` 直接进:`#instrument/#bar` 显示 ETH/4H,gate 与 `reports/ETH_USDT_4H_market_weather_router.json` 的 `current.gate` 一致。
- 下拉切换到另一个品种/周期:页面刷新为对应数据,URL 同步变化,浏览器后退能回上一个。
- 关掉 Python API:同一所选品种仍能 fallback 到 `./reports/<prefix>_*.json`(确认 fallback 用的是所选前缀,不是 BTC)。
- 选一个薄历史/无报告品种:显示"样本不足"占位,不整页崩。
- `node --check app.js` 通过。

### 依赖
- M5(已完成)、dashboard/market API(已就绪)、H5 汇总(已完成,若做 overview 表才需要)。

---

## 可选扩展(本轮可不做)
- **多品种总览表**:用 `GET /api/market/rows` / `/api/market/overview` 做一个 58 品种 × 周期的 gate 总览(按 `periodWeight` 排序/降级显示),点击进入详情页。属"多品种汇总"的完整形态,可作为 M3 的第二阶段或与 L5 一起做。
- **L5(概率语境)**:英雄卡/结论补样本数与置信标注(Step 11),独立于 M3。

## 执行建议
- 纯前端、低风险,但"fallback 一并参数化"这条最容易漏,务必验证 API-down 路径。
- 提交粒度:`feat(M3): symbol/bar selector + URL params`。
- 完成后把本文件状态改 `✅`,并在 `verification-log.md` 补一条多品种切换记录。
