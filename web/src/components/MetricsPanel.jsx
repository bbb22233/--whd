import { fmtNum, fmtPct, fmtSignedPct, dirClass, arrow } from "../lib/format.js";

// 指标工厂:密表格,所有数字 mono+tabular-nums 右对齐,方向用颜色+箭头双编码。
export default function MetricsPanel({ values }) {
  const v = values ?? {};
  const rows = [
    ["ATR", fmtPct(v.atrPct), `分位 ${fmtPct(v.atrPercentile)}`],
    ["振幅/ATR", fmtNum(v.volatilityMultiple), `分位 ${fmtPct(v.volatilityMultiplePercentile)}`],
    ["波动超额", `${fmtNum(v.remainingMomentumAtr)} ATR`, fmtPct(v.remainingMomentumPct)],
    ["量能倍率", `${fmtNum(v.volumeMultiple)}x`, "当前/20日均量"],
    ["8日", fmtSignedPct(v.d8), "短端", v.d8],
    ["13日", fmtSignedPct(v.d13), "中短", v.d13],
    ["21日", fmtSignedPct(v.d21), "中端", v.d21],
    ["34日", fmtSignedPct(v.d34), "惯性", v.d34],
    ["中值乖离", fmtSignedPct(v.middleDeviationRate), `${fmtNum(v.middleDeviationAtr)} ATR`, v.middleDeviationRate],
    ["中值位置", fmtPct(v.middlePositionPct), "峰谷区间"],
    ["233MA乖离", fmtSignedPct(v.maDeviationRate), `${fmtNum(v.maDeviationAtr)} ATR`, v.maDeviationRate],
    ["233MA位置", fmtPct(v.maPositionPct), "大周期峰谷"],
    ["趋势动能", fmtNum(v.trendScore), `${v.resonanceCount ?? "--"} 同向`, v.trendScore],
    ["拉伸热度", fmtPct(v.stretchHeat), "位置合成"],
  ];
  return (
    <section className="panel">
      <div className="panel-head"><h2>指标工厂</h2><span className="note">百分比 + ATR 尺度</span></div>
      <div className="panel-body" style={{ padding: 0 }}>
        <table className="dt">
          <thead><tr><th>指标</th><th>值</th><th>参考</th></tr></thead>
          <tbody>
            {rows.map(([k, val, sub, signed]) => (
              <tr key={k}>
                <td>{k}</td>
                <td className={`num ${signed !== undefined ? dirClass(signed) : ""}`}>
                  {signed !== undefined && Number(signed) !== 0 ? `${arrow(signed)} ` : ""}{val}
                </td>
                <td className="num" style={{ color: "var(--text-muted)" }}>{sub}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
