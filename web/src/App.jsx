import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DEFAULT_BAR, DEFAULT_INSTRUMENT, DEFAULT_SYMBOLS,
  fetchDashboard, fetchSymbols, normalizeBar, normalizeInstrument,
} from "./lib/api.js";
import Topbar from "./components/Topbar.jsx";
import GatePanel from "./components/GatePanel.jsx";
import PricePanel from "./components/PricePanel.jsx";
import ComponentGrid from "./components/ComponentGrid.jsx";
import MetricsPanel from "./components/MetricsPanel.jsx";
import { ProbabilityTable, DeviationTable } from "./components/Tables.jsx";
import NotesPanel from "./components/NotesPanel.jsx";

function scopeFromUrl() {
  const p = new URLSearchParams(window.location.search);
  return {
    instrument: normalizeInstrument(p.get("instrument")) || DEFAULT_INSTRUMENT,
    bar: normalizeBar(p.get("bar")) || DEFAULT_BAR,
  };
}

function currentCandle(candles, date) {
  const list = candles?.candles ?? [];
  const idx = list.findIndex((c) => c.date === date);
  const i = idx >= 0 ? idx : list.length - 1;
  return { candle: list[i], prev: i > 0 ? list[i - 1] : null, meta: candles?.metadata ?? {} };
}

export default function App() {
  const [scope, setScope] = useState(scopeFromUrl);
  const [symbols, setSymbols] = useState(DEFAULT_SYMBOLS);
  const [state, setState] = useState({ status: "loading" });
  const [theme, setTheme] = useState(() => localStorage.getItem("wr-theme") || "dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("wr-theme", theme);
  }, [theme]);

  useEffect(() => { fetchSymbols().then(setSymbols).catch(() => {}); }, []);

  const load = useCallback(async (sc) => {
    setState({ status: "loading" });
    try {
      const payload = await fetchDashboard(sc.instrument, sc.bar);
      if (!payload?.weather?.current) {
        setState({ status: "insufficient", metadata: payload?.weather?.metadata });
        return;
      }
      setState({ status: "ready", payload });
    } catch (err) {
      setState({ status: "error", message: String(err?.message || err) });
    }
  }, []);

  useEffect(() => { load(scope); }, [scope, load]);

  useEffect(() => {
    const onPop = () => setScope(scopeFromUrl());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const updateScope = useCallback((patch) => {
    setScope((prev) => {
      const next = {
        instrument: normalizeInstrument(patch.instrument ?? prev.instrument) || prev.instrument,
        bar: normalizeBar(patch.bar ?? prev.bar) || prev.bar,
      };
      const url = new URL(window.location.href);
      url.searchParams.set("instrument", next.instrument);
      url.searchParams.set("bar", next.bar);
      window.history.pushState(next, "", url);
      return next;
    });
  }, []);

  const meta = useMemo(() => {
    if (state.status !== "ready") return [["数据", "加载中"]];
    const m = state.payload.weather.metadata ?? {};
    return [
      ["样本", `${m.snapshotCount ?? "--"} 根`],
      ["区间", `${m.firstDate ?? "--"} → ${m.lastDate ?? "--"}`],
      ["源", state.payload.sourceMode === "dashboard_api" ? "REST" : "静态回退"],
    ];
  }, [state]);

  return (
    <div className="shell">
      <Topbar
        scope={scope}
        symbols={symbols.includes(scope.instrument) ? symbols : [scope.instrument, ...symbols]}
        meta={meta}
        theme={theme}
        onScope={updateScope}
        onReload={() => load(scope)}
        onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      />

      {state.status === "loading" && <div className="screen"><div className="big">数据加载中…</div></div>}

      {state.status === "error" && (
        <div className="screen"><div className="big">加载失败</div><div>{state.message}</div></div>
      )}

      {state.status === "insufficient" && (
        <div className="screen">
          <div className="big">样本不足</div>
          <div>{scope.instrument} {scope.bar}:历史数据不足,暂不输出灯号。</div>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
            {state.metadata?.dataStatus ?? "insufficient_history"} · 切换品种/周期试试
          </div>
        </div>
      )}

      {state.status === "ready" && <Dashboard payload={state.payload} />}

      <footer className="footer">
        {state.status === "ready"
          ? `${state.payload.weather.metadata?.routerPrinciple ?? "weather radar"} · 描述环境,非买卖信号`
          : "Market Weather Radar · 描述环境,非买卖信号"}
      </footer>
    </div>
  );
}

function Dashboard({ payload }) {
  const { weather, features, deviations, candles } = payload;
  const values = features?.current?.values ?? {};
  const { candle, prev } = currentCandle(candles, weather.current.date);
  return (
    <main className="workspace">
      {/* 左栏:灯号状态 */}
      <div className="col-left">
        <GatePanel current={weather.current} />
      </div>
      {/* 中栏:价格大图 + 主读数 + 组件状态带 + 指标 */}
      <div className="col-center">
        <PricePanel candle={candle} prevClose={prev?.close} candles={candles} values={values} />
        <ComponentGrid current={weather.current} deviations={deviations} />
        <MetricsPanel values={values} />
      </div>
      {/* 右栏:概率 + 乖离 + 读法 */}
      <div className="col-right">
        <ProbabilityTable rows={weather.currentComponentRows ?? []} />
        <DeviationTable rows={deviations?.currentRuleRows ?? []} />
        <NotesPanel weather={weather} features={features} deviations={deviations} />
      </div>
    </main>
  );
}
