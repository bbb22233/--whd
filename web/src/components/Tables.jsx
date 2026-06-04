import { fmtNum, fmtPct, fmtSignedPct, dirClass } from "../lib/format.js";

// 概率拆解:当前状态对应的历史样本(置信 + 样本数,信任校准)。
export function ProbabilityTable({ rows }) {
  const sel = (rows ?? []).filter((r) => Number(r.horizon) === 5);
  return (
    <section className="panel">
      <div className="panel-head"><h2>概率拆解</h2><span className="note">单指标历史表现</span></div>
      <div className="scroll">
        <table className="dt">
          <thead>
            <tr><th>指标</th><th>状态</th><th>置信</th><th>样本</th><th>ATR升</th><th>ATR降</th><th>振幅超</th></tr>
          </thead>
          <tbody>
            {sel.map((r, i) => (
              <tr key={i}>
                <td>{r.component}</td>
                <td>{r.state}</td>
                <td className="num">{fmtPct(r.currentConfidencePct)}</td>
                <td className="num" style={{ color: "var(--text-muted)" }}>{fmtNum(r.occurrences, 0)}</td>
                <td className="num">{fmtPct(r.atrUpProbabilityPct)}</td>
                <td className="num">{fmtPct(r.atrDownProbabilityPct)}</td>
                <td className="num">{fmtPct(r.futureRemainingMomentumPositivePct)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// 乖离规则:中值 / 233MA,只识别天气、不给买卖点。
export function DeviationTable({ rows }) {
  const sel = (rows ?? []).filter((r) => [1, 3, 5, 10].includes(Number(r.horizon)));
  return (
    <section className="panel">
      <div className="panel-head"><h2>乖离规则</h2><span className="note">只识别天气,不给买卖点</span></div>
      <div className="scroll">
        <table className="dt">
          <thead>
            <tr><th>指标</th><th>周期</th><th>状态</th><th>乖离率</th><th>ATR乖离</th><th>位置</th><th>回归</th><th>远离</th><th>置信</th></tr>
          </thead>
          <tbody>
            {sel.map((r, i) => (
              <tr key={i}>
                <td>{r.kind}</td>
                <td className="num">{r.horizon}日</td>
                <td>{r.state}</td>
                <td className={`num ${dirClass(r.deviationRate)}`}>{fmtSignedPct(r.deviationRate)}</td>
                <td className={`num ${dirClass(r.deviationAtr)}`}>{fmtNum(r.deviationAtr)}</td>
                <td className="num">{fmtPct(r.positionPct)}</td>
                <td className="num">{fmtPct(r.returnCloserProbabilityPct)}</td>
                <td className="num">{fmtPct(r.continueAwayProbabilityPct)}</td>
                <td className="num" style={{ color: "var(--text-muted)" }}>{r.confidence}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
