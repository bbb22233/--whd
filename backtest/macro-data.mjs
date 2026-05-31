export const fredSources = [
  {
    key: "dollarIndex",
    id: "DTWEXBGS",
    label: "美元指数代理",
    url: "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS"
  },
  {
    key: "us10y",
    id: "DGS10",
    label: "美国10年国债收益率",
    url: "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10"
  },
  {
    key: "fedFunds",
    id: "DFF",
    label: "有效联邦基金利率",
    url: "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF"
  },
  {
    key: "m2",
    id: "M2SL",
    label: "M2货币供应",
    url: "https://fred.stlouisfed.org/graph/fredgraph.csv?id=M2SL"
  }
];

export const stablecoinSource = {
  key: "stablecoinSupply",
  label: "稳定币总供应",
  url: "https://stablecoins.llama.fi/stablecoincharts/all"
};

export const macroFeatureDefs = [
  { key: "macroDollarIndex", label: "美元指数代理" },
  { key: "macroDollarIndex21dChangePct", label: "美元指数21日变化率" },
  { key: "macroUs10y", label: "10年美债收益率" },
  { key: "macroUs10y21dChangeBp", label: "10年美债21日变化bp" },
  { key: "macroFedFunds", label: "联邦基金利率" },
  { key: "macroFedFunds63dChangeBp", label: "联邦基金利率63日变化bp" },
  { key: "macroM2", label: "M2货币供应" },
  { key: "macroM263dChangePct", label: "M2 63日变化率" },
  { key: "macroStablecoinSupply", label: "稳定币总供应" },
  { key: "macroStablecoin63dChangePct", label: "稳定币63日变化率" },
  { key: "macroRiskPressureScore", label: "宏观风险压力" },
  { key: "macroLiquidityScore", label: "宏观流动性评分" }
];

function finite(value) {
  return Number.isFinite(value);
}

function safeDivide(numerator, denominator) {
  if (!finite(numerator) || !finite(denominator) || denominator === 0) return 0;
  return numerator / denominator;
}

function round(value, digits = 6) {
  if (!finite(value)) return null;
  return Number(value.toFixed(digits));
}

function parseNumber(value) {
  if (value === null || value === undefined || value === "" || value === ".") return null;
  const parsed = Number(value);
  return finite(parsed) ? parsed : null;
}

function dateFromTimestamp(value) {
  const timestamp = Number(value);
  if (!finite(timestamp)) return null;
  const milliseconds = timestamp > 10_000_000_000 ? timestamp : timestamp * 1000;
  return new Date(milliseconds).toISOString().slice(0, 10);
}

export function parseFredCsv(text, source) {
  const lines = text.trim().split(/\r?\n/);
  const [dateHeader, valueHeader] = (lines.shift() || "").split(",");
  if (!dateHeader || !valueHeader) return [];

  return lines.flatMap((line) => {
    const [date, value] = line.split(",");
    const parsed = parseNumber(value);
    if (!date || parsed === null) return [];
    return [{
      date,
      key: source.key,
      value: parsed
    }];
  });
}

export function parseStablecoinChart(payload) {
  const rows = Array.isArray(payload) ? payload : [];

  return rows.flatMap((item) => {
    const date = typeof item.date === "string" ? item.date.slice(0, 10) : dateFromTimestamp(item.date);
    const value = parseNumber(
      item.totalCirculatingUSD?.peggedUSD ??
      item.totalCirculating?.peggedUSD ??
      item.totalCirculatingUSD ??
      item.totalCirculating
    );

    if (!date || value === null) return [];
    return [{
      date,
      key: stablecoinSource.key,
      value
    }];
  });
}

function seriesValueOnOrBefore(seriesRows, date, cursor) {
  while (cursor.index + 1 < seriesRows.length && seriesRows[cursor.index + 1].date <= date) {
    cursor.index += 1;
  }
  return cursor.index >= 0 ? seriesRows[cursor.index].value : null;
}

function valueAgo(rows, index, lookback, key) {
  const targetIndex = index - lookback;
  if (targetIndex < 0) return null;
  return rows[targetIndex][key];
}

function pctChange(current, previous) {
  if (!finite(current) || !finite(previous) || previous === 0) return null;
  return ((current - previous) / previous) * 100;
}

function bpChange(current, previous) {
  if (!finite(current) || !finite(previous)) return null;
  return (current - previous) * 100;
}

export function buildMacroFeatureRows(candleDates, sourceRowsByKey) {
  const sortedDates = [...candleDates].sort();
  const sourceCursors = Object.fromEntries(Object.entries(sourceRowsByKey).map(([key, rows]) => [
    key,
    {
      index: -1,
      rows: [...rows].sort((left, right) => left.date.localeCompare(right.date))
    }
  ]));

  const rows = sortedDates.map((date) => {
    const dollarIndex = seriesValueOnOrBefore(sourceCursors.dollarIndex?.rows || [], date, sourceCursors.dollarIndex || { index: -1 });
    const us10y = seriesValueOnOrBefore(sourceCursors.us10y?.rows || [], date, sourceCursors.us10y || { index: -1 });
    const fedFunds = seriesValueOnOrBefore(sourceCursors.fedFunds?.rows || [], date, sourceCursors.fedFunds || { index: -1 });
    const m2 = seriesValueOnOrBefore(sourceCursors.m2?.rows || [], date, sourceCursors.m2 || { index: -1 });
    const stablecoinSupply = seriesValueOnOrBefore(sourceCursors.stablecoinSupply?.rows || [], date, sourceCursors.stablecoinSupply || { index: -1 });

    return {
      date,
      macroDollarIndex: dollarIndex,
      macroUs10y: us10y,
      macroFedFunds: fedFunds,
      macroM2: m2,
      macroStablecoinSupply: stablecoinSupply
    };
  });

  return rows.map((row, index) => {
    const dollarIndex21dChangePct = pctChange(row.macroDollarIndex, valueAgo(rows, index, 21, "macroDollarIndex"));
    const us10y21dChangeBp = bpChange(row.macroUs10y, valueAgo(rows, index, 21, "macroUs10y"));
    const fedFunds63dChangeBp = bpChange(row.macroFedFunds, valueAgo(rows, index, 63, "macroFedFunds"));
    const m263dChangePct = pctChange(row.macroM2, valueAgo(rows, index, 63, "macroM2"));
    const stablecoin63dChangePct = pctChange(row.macroStablecoinSupply, valueAgo(rows, index, 63, "macroStablecoinSupply"));
    const riskPressureScore = (
      (dollarIndex21dChangePct || 0) +
      safeDivide(us10y21dChangeBp || 0, 25) +
      safeDivide(fedFunds63dChangeBp || 0, 25) -
      safeDivide(m263dChangePct || 0, 2) -
      safeDivide(stablecoin63dChangePct || 0, 2)
    );
    const liquidityScore = -riskPressureScore;

    return {
      date: row.date,
      macroDollarIndex: round(row.macroDollarIndex),
      macroDollarIndex21dChangePct: round(dollarIndex21dChangePct),
      macroUs10y: round(row.macroUs10y),
      macroUs10y21dChangeBp: round(us10y21dChangeBp),
      macroFedFunds: round(row.macroFedFunds),
      macroFedFunds63dChangeBp: round(fedFunds63dChangeBp),
      macroM2: round(row.macroM2),
      macroM263dChangePct: round(m263dChangePct),
      macroStablecoinSupply: round(row.macroStablecoinSupply),
      macroStablecoin63dChangePct: round(stablecoin63dChangePct),
      macroRiskPressureScore: round(riskPressureScore),
      macroLiquidityScore: round(liquidityScore)
    };
  });
}

export function macroRowsToCsvRows(rows) {
  return rows.map((row) => ({
    date: row.date,
    ...Object.fromEntries(macroFeatureDefs.map((feature) => [feature.key, row[feature.key] ?? ""]))
  }));
}

export function augmentDatasetWithMacro(dataset, macroRows = []) {
  if (!macroRows.length) {
    return {
      ...dataset,
      macroEnabled: false
    };
  }

  const macroByDate = new Map(macroRows.map((row) => [row.date, row]));
  const activeFeatures = macroFeatureDefs.filter((feature) =>
    macroRows.some((row) => finite(row[feature.key]))
  );

  return {
    ...dataset,
    macroEnabled: true,
    features: [
      ...dataset.features,
      ...activeFeatures
    ],
    rows: dataset.rows.map((row) => {
      const macro = macroByDate.get(row.date) || {};
      const macroValues = Object.fromEntries(activeFeatures.map((feature) => [
        feature.key,
        macro[feature.key]
      ]).filter(([, value]) => finite(value)));

      return {
        ...row,
        values: {
          ...row.values,
          ...macroValues
        }
      };
    })
  };
}
