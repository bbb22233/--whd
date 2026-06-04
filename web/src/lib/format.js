// 数字格式化:数据密集型终端口径——固定精度、千位分隔、符号编码。
export const isNum = (v) => v !== null && v !== undefined && !Number.isNaN(Number(v));

export function fmtNum(value, digits = 2) {
  if (!isNum(value)) return "--";
  return Number(value).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

// 价格自适应精度:亚美元/低价币种用更多小数位,避免 DOGE 0.10 把开/高/低抹平。
export function fmtPrice(value) {
  if (!isNum(value)) return "--";
  const n = Math.abs(Number(value));
  let d = 2;
  if (n === 0) d = 2;
  else if (n < 0.0001) d = 8;
  else if (n < 0.01) d = 6;
  else if (n < 1) d = 5;
  else if (n < 100) d = 4;
  else if (n < 10000) d = 2;
  else d = 2;
  return Number(value).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}

export function fmtPct(value, digits = 2) {
  if (!isNum(value)) return "--";
  return `${Number(value).toFixed(digits)}%`;
}

export function fmtSignedPct(value, digits = 2) {
  if (!isNum(value)) return "--";
  const n = Number(value);
  return `${n > 0 ? "+" : ""}${n.toFixed(digits)}%`;
}

// 方向 → 语义类名(涨/跌/平),用于颜色+符号双编码
export function dirClass(value) {
  const n = Number(value);
  if (n > 0) return "up";
  if (n < 0) return "down";
  return "flat";
}

export const arrow = (value) => {
  const n = Number(value);
  if (n > 0) return "▲";
  if (n < 0) return "▼";
  return "·";
};

// 灯号 → 语义(红/黄/绿系)。返回 {tone, dot} 供颜色+符号双编码。
export function gateTone(gate) {
  if (!gate) return { tone: "flat", dot: "○" };
  if (gate.includes("红")) return gate.includes("黄") ? { tone: "warn", dot: "◐" } : { tone: "down", dot: "●" };
  if (gate.includes("黄")) return gate.includes("绿") ? { tone: "up-soft", dot: "◑" } : { tone: "warn", dot: "◐" };
  if (gate.includes("绿")) return { tone: "up", dot: "●" };
  return { tone: "flat", dot: "○" };
}

// 置信度 → High/Medium/Low(信任校准:不用裸百分比,用三档 + 数值辅助)
export function confidenceBand(pct) {
  if (!isNum(pct)) return { band: "—", tone: "flat" };
  const n = Number(pct);
  if (n >= 70) return { band: "High", tone: "up" };
  if (n >= 40) return { band: "Medium", tone: "warn" };
  return { band: "Low", tone: "down" };
}
