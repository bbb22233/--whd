---
name: frontend-craft
description: '[AUTO-LOAD] 超集技能：融合 frontend-design（审美总纲）+ google-ai-agent-design（AI交互规范）+ hermes-terminal-ui（数据密集型终端风格）。前端设计的完整工具箱。MUST load 于任何前端工作：Web组件、页面、设计原型、应用界面、Landing Page、仪表盘、AI Agent交互界面、交易终端。自动加载，覆盖 design / frontend / UI / UX / layout / landing page / AI agent / copilot / chatbot / terminal / trading / 前端。'
tags: [frontend, design, UI, UX, AI-agent, terminal, trading]
category: frontend-design
---

# frontend-craft — 前端设计超级技能

融合三大前端设计技能的精华，形成覆盖全场景的前端设计体系：

1. **frontend-design**（审美总纲）— 大胆独特的视觉方向，拒绝AI味
2. **google-ai-agent-design**（AI交互规范）— Google PAIR Guidebook + Material Design for AI
3. **hermes-terminal-ui**（数据密集型终端风格）— 量化交易终端 house style

---

## 一、架构总览：三步设计流程

```
① 确定场景类别 → ② 选择风格方向 → ③ 按指南执行
```

### ① 场景类别

首先要明确你要做什么类型的界面，因为不同场景的优先级完全不同：

| 类别 | 标志性特征 | 核心优先级 | 参考风格 |
|---|---|---|---|
| **创意型** | Landing page、品牌展示、作品集、活动页 | 视觉冲击力、独特性、情感传达 | editorial / 杂志 / 大胆实验 |
| **工具型** | SaaS后台、管理面板、设置页、工具 | 清晰性、效率、信息层次 | refined / 极简 / 实用 |
| **AI交互型** | 聊天界面、Copilot、Agent面板、AI助手 | 信任校准、可解释性、容错 | 取决于上下文（见三） |
| **数据密集型** | 交易终端、仪表盘、监控面板、Watchlist | 信息密度、数字可读性、刷新感 | industrial / 量化终端 |

### ② 风格方向选择

| 风格 | 适合 | 特征关键词 |
|---|---|---|
| **editorial / 杂志风** | 创意型 landing page | 大标题、网格打破、不对称、留白戏剧性 |
| **refined / 精致极简** | 工具型、SaaS | 极克制排版、高间距精度、微妙动效 |
| **playful / 活泼** | 年轻品牌、游戏化 | 大胆色彩、动画、圆润、有趣 |
| **industrial / 工业量化** | 数据密集型、交易终端 | 信息密度、monospace、1px边框、零装饰 |
| **maximalist / 繁复主义** | 艺术实验、独特品牌 | 丰富纹理、重叠、装饰性 |
| **luxury / 奢华** | 高端品牌 | 深色金/白、精细排版、稀有材质 |

### ③ 按指南执行

根据场景和风格，从以下章节选取对应指南。

### 场景混合：金融品牌界面

链上交易所/DEX/经纪商/Layer2 等 To B / To C 金融平台属于**混合场景**——需要同时满足：
- **品牌信任**（展示财力、建立安全感、吸引增量资金）→ 第10章
- **数据密度**（价格、深度、持仓、TVL 等实时金融数据）→ 第5章
- **交互精度**（交易表单、杠杆选择、订单簿）→ 第10章

遇到此类任务时，**同时加载第5章和第10章**。

---

## 二、通用设计思维（源于 frontend-design）

**在任何前端工作开始前，先问：**

1. **目的** — 解决什么问题？谁用？
2. **调性** — 选一个极端：不仅仅是"好看"，而是让人记住
3. **差异点** — 什么东西让这个界面 UNFORGETTABLE？
4. **约束** — 框架、性能、无障碍

**关键原则：** bold minimalism 和 refined maximalism 都能出色，关键是**有意为之**而非默认设置。

---

## 三、AI交互型界面设计规范（源于 google-ai-agent-design）

当你的界面涉及 AI Agent、聊天机器人、Copilot、或任何 LLM 驱动的交互时，遵循以下规范。

### 3.1 核心框架：人机协作的7步法

1. 找对问题 — AI 应解决真实需求，非技术先行
2. 映射现有工作流 — 理解当前用户如何解决
3. 判断 AI 是否带来独特价值 — 规则系统可能一样好
4. 自动化 vs 增强 — 自动化讨厌的任务，增强享受的任务
5. 设计奖励函数 — 明确 "成功" 的定义
6. 用假数据原型 — Wizard of Oz 方法
7. 真实用户测试

### 3.2 信任校准（关键！）

**目标不是最大化信任，而是适当信任。**

- 展示数据来源 — 告诉用户信息从哪来
- 披露局限性 — 模型没有的数据也要说
- 显示置信度 — 用 High/Medium/Low 而非百分比
- 来源引用 — 每条 AI 输出附来源

### 3.3 对话结构

- **轮次指示** — 清晰显示谁在说话
- **思考状态** — 显示 Agent 正在处理
- **流式输出** — Token 逐字显示（建立信任）
- **工具调用透明** — 显示 Agent 正在用什么工具、拿到了什么结果
- **取消支持** — 允许用户取消进行中的工具调用

### 3.4 自动化谱系

| 风险级别 | 做法 |
|---|---|
| 低风险/已建立 | 多自动化，用户控制可选 |
| 新产品类型 | 给用户更多控制 |
| 高风险 | 用户控制强制，最小化自动化 |
| 错误敏感 | 手动覆盖 + 清晰的撤销路径 |

### 3.5 错误处理

1. **诊断** — AI 错误还是上下文错误？
2. **沟通** — 用用户能懂的语言解释
3. **修正** — 提供清晰的前进路径
4. **学习** — 反馈到模型改进

**黄金法则：** "如果修正一个错误的成本比不用 AI 完成任务还高，那么 AI 并没有创造更好的体验。"

### 3.6 习惯化原则

> "如果你的 ML 算法做推荐，考虑在 UI 中预留一个特定区域，而不是把整个 UI 都建立在 ML 之上。"

- 高风险的场景需要可预测的 UI
- ML 推荐阻止了完全习惯化（用户必须"检查"）
- 把动态 ML 留给探索/开放目标
- 关键导航/任务 UI 保持在固定位置

### 3.7 设计模式清单（12条 PAIR 模式）

1. 确定 AI 是否增加价值
2. 设定合理预期
3. 解释受益，而非技术
4. 为错误负责
5. 早期投入数据实践
6. 锚定熟悉性
7. 谨慎平衡精度与召回
8. 隐私透明
9. 让探索安全
10. 让用户反馈
11. 低风险多自动化
12. 从人类来源添加上下文

---

## 四、创意/品牌型界面设计指南（源于 frontend-design）

### 4.1 排版 Typography

- **字体选择** — 避免 Arial、Inter、Roboto、系统字体。选有性格的字体
- **搭配** — 一个有特色的展示字体 + 一个精致的正文字体
- **字号层次** — 明确、大胆的层级对比

### 4.2 色彩 Color

- CSS 变量统一管理
- 主色占主导，强调色要锋利
- 忌均匀分布、畏手畏脚的调色盘

### 4.3 动效 Motion

- 优先 CSS-only 方案（HTML）或 Motion 库（React）
- **集中火力**：一个精心编排的页面加载 > 散落的小动效
- 用好 staggered reveals（animation-delay）
- 滚动触发 + 悬停惊喜

### 4.4 空间构成 Spatial

- 出人意料的布局 — 不对称、重叠、对角线流
- 打破网格的元素
- 豪放的留白 OR 有控制的密度

### 4.5 背景与细节 Backgrounds

- 氛围感与深度，不只是纯色
- 渐变网格、噪点纹理、几何图案、分层透明、戏剧阴影
- 自定义光标、谷纹叠加

### 4.6 需要避免的 AI 味

❌ 过度使用的字体：Inter、Roboto、Arial、系统字体
❌ 陈词滥调的配色：尤其紫色渐变+白底
❌ 可预测布局
❌ 缺乏上下文特征的设计

---

## 五、数据密集型界面设计规范（源于 hermes-terminal-ui）

当你的界面需要展示大量数字数据时（交易终端、监控面板、仪表盘），遵循以下规范。**信息密度第一，装饰最后。**

### 5.1 设计Tokens

```css
:root {
  /* 表面 — 暗色调去饱和石板色 */
  --bg-base:      #0B0E14;
  --bg-panel:     #11141C;
  --bg-row-alt:   #0F131B;
  --bg-hover:     #1A1F2B;
  --bg-selected:  #1E2738;

  /* 边框 */
  --border:       #232A38;
  --border-strong:#2E3848;

  /* 文字 */
  --text:         #E6EAF2;
  --text-dim:     #8A93A6;
  --text-muted:   #5A6273;

  /* 金融语义 */
  --up:           #2EBD85;
  --down:         #F6465D;
  --flat:         #8A93A6;
  --warn:         #F0A020;
  --accent:       #38BDF8;

  /* 字体 */
  --font-mono: ui-monospace, "JetBrains Mono", "IBM Plex Mono", "SF Mono", Menlo, monospace;
  --font-ui:   "Inter", ui-sans-serif, system-ui, sans-serif;

  /* 密度 */
  --row-h: 26px;
  --pad-x: 8px;
  --pad-y: 4px;
}

/* 明亮主题变体 */
[data-theme="light"] {
  --bg-base:      #F5F6F8;
  --bg-panel:     #FFFFFF;
  --bg-row-alt:   #F0F1F3;
  --bg-hover:     #EAEBED;
  --bg-selected:  #E0E2E6;
  --border:       #D0D2D8;
  --border-strong:#B8BBC4;
  --text:         #1A1D26;
  --text-dim:     #5A6273;
  --text-muted:   #8A93A6;
}
```

### 5.2 排版

| 用途 | 字体 | 字号 | 行高 | 备注 |
|---|---|---|---|---|
| 数字数据（默认） | mono | 11px | 1.25 | tabular-nums，右对齐 |
| 代码/符号 | mono | 12px | 1.25 | 大写，轻度字间距 |
| 行列标签 | ui/mono | 12px | 1.3 | --text-dim |
| 面板标题 | ui/mono | 13px | 1.3 | 大写，边框下划线 |
| 单位/轴刻度 | mono | 10px | 1.2 | --text-muted |

**不超过 ~15px。标题要安静。**

### 5.3 数字处理

- 右对齐所有数字列，左对齐文字/标签
- 固定精度（每种 instrument 固定小数位）
- 大数用千位分隔，价格保持原生精度
- 颜色按方向或偏离幅度，并配前导 +/- 或箭头 ▲/▼
- 偏离/Z-score 字段可选单元格背景染色

### 5.4 变值闪烁动画（唯一允许的动效）

数值更新时，短暂闪烁单元格背景为 --up（涨）或 --down（跌），200–300ms 衰减。用 CSS transition on background-color 实现，不改变位置/大小/透明度。

React 实现模式：

```jsx
import { useState, useEffect, useRef } from 'react'

function FlashCell({ value, children }) {
  const [flash, setFlash] = useState(null)
  const prev = useRef(value)

  useEffect(() => {
    if (value !== prev.current) {
      const dir = value > prev.current ? 'up' : 'down'
      setFlash(dir)
      prev.current = value
      const timer = setTimeout(() => setFlash(null), 250)
      return () => clearTimeout(timer)
    }
  }, [value])

  return (
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontVariantNumeric: 'tabular-nums',
        transition: 'background-color 0.2s ease',
        backgroundColor: flash === 'up'
          ? 'rgba(46,189,133,0.15)'
          : flash === 'down'
            ? 'rgba(246,70,93,0.15)'
            : 'transparent',
        padding: '0 4px',
        borderRadius: 2,
      }}
    >
      {children}
    </span>
  )
}
```

- 只改变 background-color，不改变位置/大小/透明度（避免布局抖动）
- 200–300ms 衰减（CSS transition 处理，不需要 JS 动画帧）
- 配合 useRef 存旧值做方向判断

### 5.5 布局

- 密表格 + 分割面板 > 卡片网格
- 1px 分隔线，面板边缘用 --border-strong
- 圆角 0–3px 最大
- 表格粘性表头，斑马纹可选
- 状态指示器：6–8px 圆点或 1 字符符号
- 图表：1px 线，无面积填充渐变

### 5.6 非协商原则

1. **数据是主角。** 数字，不是卡片。每像素的信号最大化。
2. **所有数字等宽。** monospace + tabular-nums，列对齐，数字不抖动。
3. **颜色承载含义，但不单独使用。** 涨/跌、多/空、超/欠范围——用颜色 AND 符号/箭头/字形，保证色盲和灰度下可读。
4. **平且安静。** 无渐变、无玻璃态、无装饰性阴影、无大圆角。1px 边框，低对比度。
5. **动效克制。** 唯一允许的动效是变值闪烁。无滑入、无淡入、无缓动花样。

---

## 六、交叉参考与场景引导

### 你的任务属于哪一类？

| 如果你要做... | 加载以下章节 |
|---|---|
| Landing page / 品牌展示 | 二 + 四 |
| SaaS 后台 / 管理面板 | 二 + refine（风格选择）|
| AI Agent / 聊天界面 / Copilot | 二 + 三（核心）+ 四或五（按视觉风格）|
| 交易终端 / 监控面板 / 仪表盘 | 二 + 五 |
| AI 交易界面 | 二 + 三（AI交互规范）+ 五（数据呈现）|
| DEX / 交易所 / 金融经纪平台 | 二 + 七（品牌信任）+ 五（数据呈现）|
| 移动端应用 | 二 + 四或五（按类型），注意触控交互 |

---

## 七、奢侈金融品牌设计规范（DEX / 交易所 / 经纪商）

当你的界面是链上交易所、DEX、永续合约平台、经纪商、或任何 To C / To B 的金融交易平台时，核心设计目的是：**展示财力、建立安全感、吸引增量资金。** 它本质上是商业金融机构的前端。

### 7.1 核心原则

1. **财富感优先** — 用户第一眼必须感受到这是一个有钱的平台。金、深蓝、宝石色系比科技紫/青更传递金融权威
2. **安全感 = 透明 + 数据** — TVL、审计记录、链上区块号、保险基金规模等数据是信任的硬通货
3. **传统金融锚定** — 用衬线字体（DM Serif Display、Baskerville）做 brand/标题，锚定传统金融的严肃感；用现代无衬线（Space Grotesk、Inter）做 UI，保持科技感
4. **品牌色贯穿每一个像素** — 不仅仅是 logo，border、hover state、active tab、focus ring 都要带品牌色
5. **信息密度但不过载** — TVL、24h Volume、Open Interest 等宏观数据用大字强调；订单簿和持仓表用密表格

### 7.2 设计Tokens（奢侈金融风格）

```css
:root {
  /* 表面 — 深蓝黑，比纯黑更有深度 */
  --bg-base:       #060A14;
  --bg-elevated:   #0B1120;
  --bg-card:       #0E1628;
  --bg-input:      #0A0F1E;
  --bg-hover:      #131D34;

  /* 边框 — 金色浸润 */
  --border:        rgba(201, 168, 76, 0.12);
  --border-gold:   rgba(201, 168, 76, 0.3);
  --border-light:  rgba(255, 255, 255, 0.06);

  /* 文字 — 暖白带金色调 */
  --text:          #EFEEE8;
  --text-dim:      #8B8A84;
  --text-muted:    #59584F;
  --text-gold:     #C9A84C;

  /* 品牌 — 金 + 蓝宝石 */
  --gold:          #C9A84C;
  --gold-soft:     rgba(201, 168, 76, 0.1);
  --gold-glow:     rgba(201, 168, 76, 0.2);
  --sapphire:      #2E6BE6;
  --sapphire-dim:  #1A3F8A;

  /* 金融语义（同第5章） */
  --up:            #2EBD85;
  --down:          #F6465D;
  --warn:          #F0A020;

  /* 字体 */
  --font-display:  'DM Serif Display', serif;  /* 衬线 = 权威感 */
  --font-ui:       'Space Grotesk', sans-serif;  /* 现代科技 */
  --font-mono:     'JetBrains Mono', monospace;
}
```

### 7.3 背景氛围

- 不要纯色背景。叠加多层径向渐变光晕（品牌色低透明度 2-4%）
- 60px 网格线纹理，`opacity: 0.04-0.06` — 暗示结构化、精密
- Top bar / Nav 用毛玻璃背景（`backdrop-filter: blur(20px)` + `background: rgba(bg, 0.85)`）
- 核心操作按钮（Connect Wallet、Trade）使用金色渐变 `linear-gradient(135deg, var(--gold), #B8922E)`
- Deep 背景可加装饰性斜线或微妙的几何图案（不超过 0.08 opacity）

### 7.4 排版层次

| 用途 | 字体 | 字号 | 备注 |
|---|---|---|---|
| Brand name / 大标题 | display (衬线) | 1.125–1.5rem | italic 可选 |
| 宏观数据 (TVL/Volume) | mono | 1.25rem | 金色或白色 |
| 价格/交易数据 | mono | 0.9375–1.125rem | tabular-nums |
| 面板标题 | ui | 0.75rem | uppercase + letter-spacing |
| 表单/操作按钮文本 | ui | 0.8125rem | 字重600-700 |
| 标签/辅助文字 | ui/mono | 0.625–0.6875rem | --text-muted 色 |

### 7.5 关键组件设计

**Stats Bar（TVL/Volume/OI）：**
- 4列 1px 金色边框分割，每列背景 `--bg-card`
- 宏观数字用大号 mono，变化值用颜色+符号同时编码
- 标签小写大写（uppercase），`--text-muted` 色

**交易面板（Swap / Perp）：**
- 双标签 Long/Short 或 Buy/Sell，active tab 下划金色线
- Market selector 显示交易对+当前价格+24h变化
- 杠杆选择器：8根金色 notch 横条（1×–100×），active 亮金
- 输入框：深色背景 `--bg-input`，focus 时金色边框
- Open Long / Open Short 按钮：渐变背景 + 对应涨/跌色 + hover glow 阴影

**Order Book：**
- 10档 Asks（红色）+ 10档 Bids（绿色）+ 中间 Mark Price
- depth bar 可视化（占位绝对定位，`opacity: 0.08`）
- 中间价用金色大字，带 Spread 显示

**持仓表：**
- 7列（Pair / Dir / Size / Entry / Mark / PnL / Liq）
- Direction 列颜色编码（Long=绿色 Short=红色）
- PnL 列用 +/- 符号+颜色双编码
- Tab 切换：Positions / Open Orders / History

**Connect Wallet：**
- 金色渐变按钮，hover 时金色发光阴影
- 链状态指示：绿色圆点 + 区块号（透明展示链上状态）

### 7.6 需要避免的

❌ 科技紫+青色调（更适合 consumer app，不适合金融机构）
❌ 纯黑背景（没深度，显得廉价）
❌ 大圆角 card（DEX 交易界面圆角不超过 10-16px）
❌ 过度动画（金融界面需要实时感，不是炫技）
❌ 只有一个品牌色（需要主色+辅助色+强调色的三角体系）
❌ 用 emoji 做状态指示器（用字体图标或几何符号）

### 7.7 常见交互模式

- **杠杆选择**：点击 notch 立即生效，数值实时显示在右侧
- **金额输入**：placeholder 显示 "0.00"，MAX 按钮快速填仓
- **Long/Short 切换**：切换时表单字段保留但详情数值重新计算
- **Order Book 悬停**：hover 行高亮，可点击快速填价
- **表格排序**：持仓表表头可点击排序
- **Tab 切换**：Positions / Open Orders / History 三态切换

---

## 八、交付规范

每次交付前端界面时，按以下格式输出：

```
MEDIA:<截图路径>
---

**<项目名>** ✅

运行在 `http://<host>:<port>`，项目 `<abs-path>`

**设计：** 场景类别 + 风格方向

设计说明包含：
- 布局架构（简要描述或 ASCII 布局图）
- 从哪个技能章节取了什么规范
- 关键设计决策（色彩、字体、布局选择）
- 交互功能一览
```

### 项目脚手架 — 搭配 vite-frontend-project 使用

本技能负责"做成什么样"——视觉方向、排版体系、色彩系统、动效策略。
`vite-frontend-project` 技能负责"怎么跑起来"——项目创建、依赖安装、dev server、构建部署。

当用户要交付一个可运行的 URL 时，同时加载这两个技能：

```
skill_view("frontend-craft")          # 设计规范
skill_view("vite-frontend-project")   # 工程脚手架
```

---

## 九、参考文件

本技能下的参考文件（实际存在，可直接加载）：

- `references/lumina-landing-fusion.md` — Lumina landing page 工作示例：创意型 + editorial/杂志风
- `references/gridbot-dashboard-implementation.md` — GridBot 量化网格参数仪表盘：数据密集型 + industrial 风格
- `references/nexus-dex-implementation.md` — Nexus DEX 永续合约交易界面：金融品牌混合型 + luxury + industrial 融合风格
- `references/telegram-mini-app-nextjs.md` — Telegram Mini App + Next.js 调试笔记：RSC白屏修复、header编码问题、HMR兼容性、tunnel测试配置

以下文件来自原始继承技能，不在本目录下。如需引用，在 Hermes Agent 中用 `skill_view()` 加载：

- `google-ai-agent-design` / `references/google-ai-agent-design.md` — Google PAIR + Material Design for AI 完整原文（原 frontend-design 子技能）
- `hermes-terminal-ui` / `references/terminal-atr-panel.md` — Hermes 交易终端 ATR 面板实现模式（原 hermes-terminal-ui 子技能）

---

## 十、快速清单

### 开始前
- [ ] 场景分类（创意/工具/AI/数据密集型？）
- [ ] 风格方向选择
- [ ] 差异化锚点（让人记住什么？）

### 执行中
- [ ] 排版体系（字体搭配、字号层次）
- [ ] 色彩体系（CSS变量、主色+强调色）
- [ ] 动效策略（集中而非散落）
- [ ] 空间布局（层次、留白、打破规则）
- [ ] 背景与氛围（质感、纹理）

### AI界面额外
- [ ] 信任校准（来源、置信度、局限性）
- [ ] 对话结构（轮次、思考态、流式）
- [ ] 错误处理路径（诊断→沟通→修正→学习）
- [ ] 自动化谱系匹配风险等级

### 数据密集界面额外
- [ ] 所有数字 monospace + tabular-nums
- [ ] 颜色+符号双重编码
- [ ] 变值闪烁动画就位
- [ ] 信息密度最大化，装饰最小化

### 金融品牌界面额外（DEX/交易所/经纪商）
- [ ] 品牌色系（主色+辅助色+强调色 三角体系）
- [ ] 衬线展示字体锚定传统金融权威感
- [ ] 背景多层纹理（光晕+网格线+毛玻璃）
- [ ] 宏观数据大字强调（TVL/Volume/OI）
- [ ] 交易交互组件（杠杆选择/表单/Order Book/持仓表）
