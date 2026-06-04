# frontend-craft 融合案例：GridBot 量化网格参数仪表盘

**场景：** 数据密集型
**风格：** industrial / 量化终端
**框架：** React + Vite + recharts

## 从三个技能汲取的精华

### hermes-terminal-ui → 核心规范（占比最高）
- 完整的设计 tokens（`--bg-base: #0B0E14` / `--font-mono: JetBrains Mono` / 金融语义颜色）
- 所有数字 monospace + tabular-nums
- Panel 架构：标题栏 + body，1px 边框，0 装饰
- 颜色+符号双编码：涨=绿+▲/↓，跌=红+▼/↑
- 信息密度：28px 行高，10px 内边距，无留白

### frontend-design → 排版细节
- Inter 系统 UI 字体 + JetBrains Mono 数字字体
- 面板标题大写 `text-transform: uppercase` + `letter-spacing: 0.06em`
- 状态指示器用颜色+字形(`●` `◌` `○`)

### google-ai-agent-design → 未直接使用
- 本界面无 AI 交互组件，按 frontend-craft 第6章场景指引，不加载第3章

## 布局架构

```
┌─Sidebar──┬─Top Bar──────────────┐
│ 220px    │ GridBot · LIVE · API │
│          ├──────────────────────┤
│ ◈ Grid   │ 左列         右列    │
│ ▦ Config │ StatCard×4  PnL图表  │
│ ◉ Pos.   │ GridParams  Spread   │
│ ◴ Hist.  │ DynMetrics  OrderBook│
│ ⚙ Sett.  │             Grids表  │
└──────────┴──────────────────────┘
```

## 核心组件模式

### StatCard
```jsx
<StatCard label="Total PnL" value="+$429.95" sub="ROI +4.91%" color="up" />
```
- 4列 grid，背景 `--bg-card`，1px border
- label 小写 uppercase，value monospace + tabular-nums
- color prop: "up"/"down"/"neutral" 控制文字色

### Grid Parameters
- 2列 grid 表单布局，每个 param-group 包含 label（带字段名）+ input
- input 背景 `--bg-input`，聚焦时 `--accent` 边框
- 混合可编辑(numeric input) + 只读(readOnly)字段

### Toggle Switch
```jsx
<Toggle label="Trailing Activation" checked={liveMode} onChange={...} />
```
- 32×18 track，14×14 thumb，`.on` 类切换 `--up` 背景
- 模拟开关，onChange 回调更新父组件 state

### FlashCell（变值闪烁）
```jsx
<FlashCell value={price}>
  ${price.toFixed(2)}
</FlashCell>
```
- useRef 存旧值做方向判断（涨→绿闪，跌→红闪）
- 200ms CSS transition on background-color 衰减
- 只改变背景色，不改变位置/大小/透明度（避免布局抖动）

完整实现见 frontend-craft SKILL.md 第 5.4 节。

### Order Book Mini
- Asks（红色）反转显示，Bids（绿色）正序
- 中间价格行用 warn 色 + 分割线
- 数据格式：price（mono + 颜色）+ vol（mono + muted）

### Grids Table
- 7列：Symbol / Status / Grid PnL / PnL% / APR / Orders / Price
- Status 用颜色+符号双编码（● 绿=active, ◌ 琥珀=paused, ○ 灰=filled）
- 数值列对齐，符号列左对齐

## 设计 tokens 使用清单

| 用途 | 变量 | 值 |
|---|---|---|
| 页面背景 | --bg-base | #0B0E14 |
| 面板背景 | --bg-panel | #11141C |
| 卡片背景 | --bg-card | #131822 |
| 输入框背景 | --bg-input | #0D1018 |
| 边框 | --border | #232A38 |
| 边框强调 | --border-strong | #2E3848 |
| 主文字 | --text | #E6EAF2 |
| 次文字 | --text-dim | #8A93A6 |
| 弱文字 | --text-muted | #5A6273 |
| 涨/多 | --up | #2EBD85 |
| 跌/空 | --down | #F6465D |
| 警告 | --warn | #F0A020 |
| 强调 | --accent | #38BDF8 |

## 预览

项目 `/root/grid-dashboard/`
