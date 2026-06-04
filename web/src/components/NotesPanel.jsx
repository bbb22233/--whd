import { fmtNum, fmtPct, fmtSignedPct } from "../lib/format.js";

export default function NotesPanel({ weather, features, deviations }) {
  const c = weather.current;
  const v = features?.current?.values ?? {};
  const notes = [
    ["主结论", `${c.gate},当前更像「${c.topWeatherRoute}」天气,分 ${fmtNum(c.topWeatherScore, 1)}。`],
    ["波动", `ATR 处 ${fmtPct(v.atrPercentile)} 分位,振幅/ATR ${fmtNum(v.volatilityMultiple)},历史 5 日后 ATR 降低概率 ${fmtPct(c.fiveDayAtrDownProbabilityPct)}。`],
    ["乖离", `中值乖离 ${fmtSignedPct(v.middleDeviationRate)}(${fmtNum(v.middleDeviationAtr)} ATR);233MA 乖离 ${fmtSignedPct(v.maDeviationRate)}(${fmtNum(v.maDeviationAtr)} ATR)。`],
    ["规则", deviations?.finalWeather?.riskNote ?? "当前规则只做天气识别,不单独触发交易。"],
  ];
  return (
    <section className="panel notes">
      <div className="panel-head"><h2>当前读法</h2><span className="note">解释</span></div>
      <div className="panel-body">
        {notes.map(([k, text]) => (
          <div className="item" key={k}><b>{k}</b> {text}</div>
        ))}
      </div>
    </section>
  );
}
