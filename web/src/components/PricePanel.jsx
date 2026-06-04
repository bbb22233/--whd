import { fmtNum, fmtPrice, fmtSignedPct, dirClass } from "../lib/format.js";
import FlashCell from "./FlashCell.jsx";
import PriceChart from "./PriceChart.jsx";

export default function PricePanel({ candle, prevClose, candles, values }) {
  const daily = candle && prevClose ? (candle.close / prevClose - 1) * 100 : null;
  const intraday = candle ? (candle.close / candle.open - 1) * 100 : null;
  const cells = [
    ["开", fmtPrice(candle?.open)],
    ["高", fmtPrice(candle?.high)],
    ["低", fmtPrice(candle?.low)],
    ["日内", fmtSignedPct(intraday)],
    ["振幅", values?.rangePct != null ? `${fmtNum(values.rangePct)}%` : "--"],
    ["量", fmtNum(candle?.volume, 0)],
  ];
  return (
    <section className="panel area-price">
      <div className="panel-head">
        <h2>盘口快照</h2>
        <span className="note">{candle?.date ?? "--"}</span>
      </div>
      <div className="panel-body">
        <div className="price-main">
          <FlashCell value={candle?.close} className="last mono">{fmtPrice(candle?.close)}</FlashCell>
          <span className={`change ${dirClass(daily)}`}>{fmtSignedPct(daily)}</span>
        </div>
        <div className="quote-grid">
          {cells.map(([k, v]) => (
            <div className="qcell" key={k}><div className="k">{k}</div><div className="v">{v}</div></div>
          ))}
        </div>
        <PriceChart candles={candles} />
      </div>
    </section>
  );
}
