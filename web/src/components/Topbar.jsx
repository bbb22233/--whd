import { SUPPORTED_BARS } from "../lib/api.js";

export default function Topbar({ scope, symbols, meta, theme, onScope, onReload, onToggleTheme }) {
  return (
    <header className="topbar">
      <div className="brand">
        <span className="eyebrow">Market Weather Radar</span>
        <span className="title">
          {scope.instrument}
          <span className="sep">/</span>
          {scope.bar}
        </span>
      </div>

      <div className="selectors">
        <div className="field">
          <label htmlFor="sym">品种</label>
          <select id="sym" value={scope.instrument} onChange={(e) => onScope({ instrument: e.target.value })}>
            {symbols.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="bar">周期</label>
          <select id="bar" value={scope.bar} onChange={(e) => onScope({ bar: e.target.value })}>
            {SUPPORTED_BARS.map((b) => (
              <option key={b} value={b}>{b}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="meta-chips">
        {meta.map(([k, v]) => (
          <span className="chip" key={k}>{k}: <strong>{v}</strong></span>
        ))}
      </div>

      <span className="spacer" />
      <button className="icon-btn" title="切换主题" onClick={onToggleTheme}>{theme === "dark" ? "☀" : "☾"}</button>
      <button className="icon-btn" title="刷新" onClick={onReload}>↻</button>
    </header>
  );
}
