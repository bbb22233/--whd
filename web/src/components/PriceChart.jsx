import { LineChart, Line, YAxis, XAxis, Tooltip, ResponsiveContainer } from "recharts";

// 第五章:图表 1px 线,无面积填充渐变,安静。取最近 ~120 根收盘。
export default function PriceChart({ candles }) {
  const rows = (candles?.candles ?? []).slice(-120).map((c) => ({ date: c.date, close: Number(c.close) }));
  if (rows.length < 2) return null;
  const up = rows[rows.length - 1].close >= rows[0].close;
  const stroke = up ? "var(--up)" : "var(--down)";
  return (
    <div style={{ height: 120, marginTop: 10 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <XAxis dataKey="date" hide />
          <YAxis domain={["dataMin", "dataMax"]} hide />
          <Tooltip
            contentStyle={{ background: "var(--bg-card)", border: "1px solid var(--border-strong)", borderRadius: 3, fontSize: 11 }}
            labelStyle={{ color: "var(--text-dim)", fontFamily: "var(--font-mono)" }}
            itemStyle={{ color: "var(--text)", fontFamily: "var(--font-mono)" }}
            formatter={(v) => [Number(v).toLocaleString("en-US"), "close"]}
          />
          <Line type="monotone" dataKey="close" stroke={stroke} strokeWidth={1} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
