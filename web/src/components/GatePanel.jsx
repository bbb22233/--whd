import { fmtNum, fmtPct, gateTone, confidenceBand, isNum } from "../lib/format.js";

// 总闸灯号 + 信任校准(第三章):样本/置信用 High/Med/Low + 数值,小样本弱化 + 红线提示。
export default function GatePanel({ current }) {
  const { tone, dot } = gateTone(current.gate);
  const occ = Number(current.topWeatherOccurrences);
  const conf = Number(current.topWeatherSampleConfidencePct);
  const gateWord = current.topWeatherConfidenceGate;
  const lowSample = (isNum(occ) && occ < 30) || (gateWord && !String(gateWord).includes("通过"));
  const cb = confidenceBand(conf);

  return (
    <section className={`panel gate ${lowSample ? "low-sample" : ""}`}>
      <div className="panel-head">
        <h2>总闸门</h2>
        <span className="note">描述当下环境 · 非买卖信号</span>
      </div>
      <div className="panel-body">
        <div className="gate-line">
          <span className={`light t-${tone}`}><span className="dot">{dot}</span>{current.gate || "--"}</span>
          <span className="route">最像 <b>{current.topWeatherRoute || "--"}</b> · 分 {fmtNum(current.topWeatherScore, 1)}</span>
        </div>

        <p className="summary">{current.weatherSummary || "—"}</p>
        <p className="bias">倾向:{current.actionBias || "—"}</p>

        <div className="calib">
          <span className="cchip"><span className="k">样本</span><span className="v mono">{isNum(occ) ? `${occ}次` : "--"}</span></span>
          <span className="cchip"><span className="k">置信</span><span className={`v mono band-${cb.tone}`}>{cb.band}{isNum(conf) ? ` ${fmtPct(conf, 0)}` : ""}</span></span>
          <span className="cchip"><span className="k">样本闸</span><span className="v">{gateWord || "--"}</span></span>
        </div>

        {lowSample && (
          <div className="caveat">⚠ 样本偏少({isNum(occ) ? occ : "--"}次),概率仅供参考、勿当确定性。</div>
        )}
        <div className="disclaimer">雷达只识别"现在是什么环境",不预测涨跌、不给买卖点。盈亏自负。</div>
      </div>
    </section>
  );
}
