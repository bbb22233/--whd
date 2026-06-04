import { fmtNum, fmtPct } from "../lib/format.js";

// 状态卡:波动/超额/短ATR/位置/大周期/趋势量能。颜色+符号双编码由文案+状态名承载。
export default function ComponentGrid({ current, deviations }) {
  const ruleOf = (kindKey, h = 10) =>
    (deviations?.currentRuleRows ?? []).find((r) => r.kindKey === kindKey && Number(r.horizon) === h);
  const middle = ruleOf("middle");
  const ma = ruleOf("ma233");

  const cards = [
    { t: "波动状态", s: current.volatilityState, a: `降波 ${fmtPct(current.fiveDayAtrDownProbabilityPct)}`, b: `升波 ${fmtPct(current.fiveDayAtrUpProbabilityPct)}` },
    { t: "波动超额", s: current.remainingMomentumState, a: `${fmtNum(current.remainingMomentumAtr)} ATR`, b: `转正 ${fmtPct(current.fiveDayFutureMomentumPositivePct)}` },
    { t: "短 ATR", s: current.shortAtrState ?? "—", a: `3/21 ${fmtNum(current.atr3To21)}`, b: `8/21 ${fmtNum(current.atr8To21)}` },
    { t: "短期位置", s: current.middleState, a: `${fmtNum(current.middleDeviationAtr)} ATR`, b: `回归 ${fmtPct(middle?.returnCloserProbabilityPct ?? current.middleTenDayReturnCloserPct)}` },
    { t: "大周期过滤", s: current.maState, a: `${fmtNum(current.maDeviationAtr)} ATR`, b: `远离 ${fmtPct(ma?.continueAwayProbabilityPct ?? current.maTenDayContinueAwayPct)}` },
    { t: "趋势 / 量能", s: `${current.trendState} / ${current.volumeState}`, a: `共振 ${current.resonanceCount ?? "--"}`, b: `量 ${fmtNum(current.volumeMultiple)}x` },
  ];

  return (
    <section className="panel">
      <div className="panel-head"><h2>组件状态</h2><span className="note">环境分解</span></div>
      <div className="comp-grid">
        {cards.map((c) => (
          <article className="comp-card" key={c.t}>
            <div className="ct">{c.t}</div>
            <div className="cs">{c.s ?? "—"}</div>
            <div className="ck"><span>{c.a}</span><b>{c.b}</b></div>
          </article>
        ))}
      </div>
    </section>
  );
}
