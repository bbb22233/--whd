# frontend-craft 融合案例：Lumina Landing Page

**场景：** 创意型
**风格：** editorial / 杂志风
**框架：** React + Vite + CSS (Intersection Observer scroll-reveal)

## 从三个技能汲取的精华

### frontend-design → 视觉方向
- 暖白编辑基底 `#F7F6F2` 搭配琥珀橙 accent `#D35400` + 墨绿 `#0A7E6E`
- 不对称布局：hero card 旋转 -2°，offset 浮动标签
- DM Sans 全系字体（展示+正文统一样式）
- 噪点纹理叠加、光标跟随光晕

### google-ai-agent-design → 信任元素
- Hero 卡片底部：置信度条形图（High / Medium / Low）+ 数据来源标注
- Badge 显示实时设计师数量 `2,847`（具体数字比"数千"更有说服力）
- "trained on 2.4M designs" — 透明披露训练数据规模

### hermes-terminal-ui → 数据规范
- 所有统计数字使用 `font-family: var(--font-mono)` + `font-variant-numeric: tabular-nums`
- 指标数值直接用 monospace 呈现：`8,421` / `94%` / `12×`
- 数值颜色 + 符号双编码（涨幅用绿色 + +号）

## 关键代码段

### 信任指示器（Hero）

```jsx
<div className="hero-card-trust">
  <div className="trust-meter">
    <span>Confidence</span>
    <div className="trust-bar">
      <div className="trust-bar-fill" />
    </div>
    <span className="trust-check">High</span>
  </div>
  <span className="trust-source">trained on 2.4M designs</span>
</div>
```

### Monospace 数字

```jsx
<span className="num">2,847</span>
```

CSS：
```css
.num {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}
```

## Layout 架构

```
┌─Nav───────────────────┐
├─Hero──────────────────┤
│ Col 1          Col 2  │
│ Tag: beta      Card   │
│ H1: Design     ┌────┐ │
│ thinks with    │grid│ │
│ you            │    │ │
│ CTA btn ×2     │trust││
│ Stats 12× 94%  └────┘ │
│ 8,421                 │
├─Features──────────────┤
│ 3-col grid, 6 items   │
├─Showcase──────────────┤
│ Text + Metrics Chart  │
├─Testimonials──────────┤
│ 3-col cards           │
├─CTA───────────────────┤
├─Footer────────────────┤
```

## 预览

项目 `/root/product-landing/`
