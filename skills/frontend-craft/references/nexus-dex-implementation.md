# frontend-craft 融合案例：Nexus DEX 永续合约交易界面

**场景：** 金融品牌（混合型 — 品牌信任 + 数据密集 + 交互精度）
**风格：** luxury + industrial 双风格融合
**框架：** React + Vite (无第三方 UI 库)

## 设计要点

### 品牌定位

"展示财力、建立安全感、吸引增量资金"——这是商业金融机构前端的核心设计目的。

### 从三个技能汲取的精华

| 技能 | 贡献 |
|---|---|
| **frontend-design** (品牌总纲) | DM Serif Display 衬线字体锚定传统金融权威感，金+蓝宝石+深蓝黑的三角品牌色系，多层背景纹理 |
| **hermes-terminal-ui** (数据规范) | 所有数字 monospace + tabular-nums，涨跌色+符号双编码，Order Book / Positions 密表格，1px 低对比边框 |
| **google-ai-agent-design** (信任机制) | 链上区块号透明展示（`#18,423,592`），Connect Wallet 状态灯，数据来源可视化 |

### 关键设计决策

1. **`#060A14` 深蓝黑** — 比纯黑更有深度，比纯蓝更稳重
2. **`#C9A84C` 暖金** — 财富感锚点，用于 border、active 状态、gold glow shadow、品牌 logo
3. **`#2E6BE6` 蓝宝石** — 科技实力冷色，与金色形成互补三角
4. **DM Serif Display italic** — brand name 用衬线斜体，暗示传统金融的权威和优雅
5. **Space Grotesk** — UI 字体，干净现代，不抢戏
6. **背景层级** — 径向光晕 + 60px 网格线 + 毛玻璃 topbar，多层叠加制造深度感

### 交互功能一览

- Long/Short 交易方向切换（tab + 表单动态联动）
- 8档杠杆快速选择器（点击 notch 即时生效）
- 金额输入 + MAX 按钮
- 交易详情实时计算（Entry Price / Liquidation / Margin / Fee）
- Open Long / Open Short 操作按钮（渐变色 + hover glow）
- Order Book 10档 Asks + 10档 Bids + 深度条可视化
- 持仓表 7列数据 + 颜色编码方向/PnL
- Positions / Open Orders / History 三态 Tab 切换

### 布局架构

```
┌─Top Bar───────────────────────────────────────┐
│ Brand(N) · Trade Markets Portfolio Earn  │ ⋮ │
│                                    [Connect] │
├───────────────────────────────────────────────┤
│ TVL $2.84B  │ Vol $847.2M │ OI $1.24B │ Liq $12.8M │
├──────────────────────┬────────────────────────┤
│  ┌─Trade Panel────┐  │  ┌─Order Book─────────┐│
│  │ [Long] [Short] │  │  │ Price  Size Total  ││
│  │ ETH/USDC Perp  │  │  │ Asks (10 rows)     ││
│  │ $3,508.20      │  │  │ ──────$3,508.20── ││
│  │ Leverage: 5×   │  │  │ Bids (10 rows)     ││
│  │ ▓▓▓▓▓░░░░░ 100×│  │  └────────────────────┘│
│  │ Size [___] MAX │  │                         │
│  │ [Open Long] [Short]│                       │
│  └────────────────┘  │                         │
│  ┌─Positions────────┐│                         │
│  │Pos.|Orders|Hist. ││                         │
│  │Pair  Dir Size... ││                         │
│  │ETH/USDC Lng 42.5 ││                         │
│  └──────────────────┘│                         │
└──────────────────────┴────────────────────────┘
```

## 完整代码

项目路径：`/root/nexus-dex/`
运行地址：`http://localhost:4173`

### 核心 tokens (`App.css`)

```css
--bg-base:       #060A14;
--gold:          #C9A84C;
--sapphire:      #2E6BE6;
--font-display:  'DM Serif Display', serif;
--font-ui:       'Space Grotesk', sans-serif;
--font-mono:     'JetBrains Mono', monospace;
```

### 核心组件模式

**Stats Block：**
```jsx
<div className="stat-block">
  <div className="stat-label">Total Value Locked</div>
  <span className="stat-number">$2.84B</span>
  <span className="stat-change up">+12.4%</span>
</div>
```

**Leverage Selector（8 档 notch）：**
```jsx
<div className="lev-track">
  {[1,2,3,5,10,20,50,100].map(n => (
    <div key={n} className={`lev-notch ${n <= value ? 'active' : ''}`}
         onClick={() => onChange(n)} />
  ))}
</div>
```

**Trade Buttons（渐变 + glow）：**
```jsx
<button className="btn-long" style={{
  background: 'linear-gradient(135deg, rgba(46,189,133,0.15), rgba(46,189,133,0.05))',
  border: '1px solid rgba(46,189,133,0.2)',
}}>Open Long</button>
```

**Order Book Row（depth bar）：**
```jsx
<div className="order-row">
  <span className="asks">{price.toFixed(2)}</span>
  <span className="vol">{vol.toFixed(1)}</span>
  <span className="total">{total.toFixed(1)}</span>
  <div className="depth-bar ask" style={{ width: `${depth}%` }} />
</div>
```
