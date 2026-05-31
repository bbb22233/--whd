import { buildIndicatorSnapshots } from "./indicators.mjs";
import { stateFeatureDefs } from "./state-features.mjs";

const bucketDefs = [
  { name: "极低", min: 0, max: 10 },
  { name: "偏低", min: 10, max: 30 },
  { name: "中性", min: 30, max: 70 },
  { name: "偏高", min: 70, max: 90 },
  { name: "极高", min: 90, max: 100.000001 }
];

function finite(value) {
  return Number.isFinite(value);
}

function safeDivide(numerator, denominator) {
  if (!finite(numerator) || !finite(denominator) || denominator === 0) return 0;
  return numerator / denominator;
}

function average(values) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function median(values) {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function round(value, digits = 4) {
  if (!finite(value)) return 0;
  return Number(value.toFixed(digits));
}

function inWindow(date, config) {
  if (config.fromDate && date < config.fromDate) return false;
  if (config.toDate && date > config.toDate) return false;
  return true;
}

function bucketForRank(rankPct) {
  return bucketDefs.find((bucket) => rankPct >= bucket.min && rankPct < bucket.max) || bucketDefs.at(-1);
}

function futureStats(candles, index, horizon) {
  const entry = candles[index];
  const future = candles.slice(index + 1, index + 1 + horizon);
  if (!entry || future.length < horizon) return null;

  const exit = future.at(-1);
  const maxHigh = Math.max(...future.map((candle) => candle.high));
  const minLow = Math.min(...future.map((candle) => candle.low));
  const futureReturnPct = safeDivide(exit.close - entry.close, entry.close) * 100;
  const maxUpPct = safeDivide(maxHigh - entry.close, entry.close) * 100;
  const maxDownPct = safeDivide(minLow - entry.close, entry.close) * 100;

  return {
    futureReturnPct,
    absReturnPct: Math.abs(futureReturnPct),
    maxUpPct,
    maxDownPct,
    excursionPct: maxUpPct - maxDownPct
  };
}

function observationRowsForFeature(feature, snapshots, candles, config) {
  const observations = snapshots
    .map((snapshot) => ({
      date: snapshot.date,
      index: snapshot.index,
      close: snapshot.price.last,
      value: feature.pick(snapshot)
    }))
    .filter((row) => finite(row.value))
    .sort((left, right) => left.value - right.value);

  const ranked = observations.map((row, rankIndex) => {
    const rankPct = observations.length <= 1 ? 50 : (rankIndex / (observations.length - 1)) * 100;
    const bucket = bucketForRank(rankPct);

    return {
      ...row,
      indicator: feature.label,
      indicatorKey: feature.key,
      rankPct,
      bucket: bucket.name,
      bucketRange: `${bucket.min}-${Math.min(bucket.max, 100)}%`
    };
  });

  return ranked.flatMap((row) => config.horizons.flatMap((horizon) => {
    const stats = futureStats(candles, row.index, horizon);
    if (!stats) return [];

    return [{
      indicator: row.indicator,
      indicatorKey: row.indicatorKey,
      date: row.date,
      close: round(row.close, 2),
      value: round(row.value),
      rankPct: round(row.rankPct, 2),
      bucket: row.bucket,
      bucketRange: row.bucketRange,
      horizon,
      futureReturnPct: round(stats.futureReturnPct),
      absReturnPct: round(stats.absReturnPct),
      maxUpPct: round(stats.maxUpPct),
      maxDownPct: round(stats.maxDownPct),
      excursionPct: round(stats.excursionPct)
    }];
  }));
}

function summarizeObservationRows(rows) {
  const groups = new Map();

  for (const row of rows) {
    const key = `${row.indicatorKey}::${row.bucket}::${row.horizon}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }

  return Array.from(groups.values()).map((groupRows) => {
    const first = groupRows[0];
    const values = groupRows.map((row) => row.value);
    const returns = groupRows.map((row) => row.futureReturnPct);
    const absReturns = groupRows.map((row) => row.absReturnPct);
    const maxUps = groupRows.map((row) => row.maxUpPct);
    const maxDowns = groupRows.map((row) => row.maxDownPct);
    const excursions = groupRows.map((row) => row.excursionPct);

    return {
      indicator: first.indicator,
      indicatorKey: first.indicatorKey,
      bucket: first.bucket,
      bucketRange: first.bucketRange,
      horizon: first.horizon,
      occurrences: groupRows.length,
      valueMin: round(Math.min(...values)),
      valueMedian: round(median(values)),
      valueMax: round(Math.max(...values)),
      avgReturnPct: round(average(returns)),
      medianReturnPct: round(median(returns)),
      upRatePct: round(safeDivide(groupRows.filter((row) => row.futureReturnPct > 0).length, groupRows.length) * 100, 2),
      avgAbsReturnPct: round(average(absReturns)),
      avgMaxUpPct: round(average(maxUps)),
      avgMaxDownPct: round(average(maxDowns)),
      avgExcursionPct: round(average(excursions)),
      lastSeen: groupRows.at(-1)?.date || ""
    };
  }).sort((left, right) =>
    left.indicator.localeCompare(right.indicator, "zh-CN") ||
    left.horizon - right.horizon ||
    bucketOrder(left.bucket) - bucketOrder(right.bucket)
  );
}

function bucketOrder(name) {
  return bucketDefs.findIndex((bucket) => bucket.name === name);
}

function contrastRows(summaryRows) {
  const groups = new Map();

  for (const row of summaryRows) {
    const key = `${row.indicatorKey}::${row.horizon}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }

  return Array.from(groups.values()).flatMap((rows) => {
    const low = rows.find((row) => row.bucket === "极低");
    const high = rows.find((row) => row.bucket === "极高");
    if (!low || !high) return [];

    return [{
      indicator: low.indicator,
      indicatorKey: low.indicatorKey,
      horizon: low.horizon,
      lowOccurrences: low.occurrences,
      highOccurrences: high.occurrences,
      lowValueMedian: low.valueMedian,
      highValueMedian: high.valueMedian,
      lowAvgReturnPct: low.avgReturnPct,
      highAvgReturnPct: high.avgReturnPct,
      highMinusLowReturnPct: round(high.avgReturnPct - low.avgReturnPct),
      lowAvgAbsReturnPct: low.avgAbsReturnPct,
      highAvgAbsReturnPct: high.avgAbsReturnPct,
      highMinusLowAbsReturnPct: round(high.avgAbsReturnPct - low.avgAbsReturnPct),
      lowAvgExcursionPct: low.avgExcursionPct,
      highAvgExcursionPct: high.avgExcursionPct,
      highMinusLowExcursionPct: round(high.avgExcursionPct - low.avgExcursionPct)
    }];
  }).sort((left, right) =>
    left.indicator.localeCompare(right.indicator, "zh-CN") ||
    left.horizon - right.horizon
  );
}

export function runIndicatorBacktest(cleanPayload, config) {
  const snapshots = buildIndicatorSnapshots(cleanPayload.candles, config).filter((snapshot) => inWindow(snapshot.date, config));
  const observationRows = stateFeatureDefs.flatMap((feature) =>
    observationRowsForFeature(feature, snapshots, cleanPayload.candles, config)
  );
  const summaryRows = summarizeObservationRows(observationRows);

  return {
    metadata: {
      instrument: cleanPayload.metadata.instrument,
      bar: cleanPayload.metadata.bar,
      fromDate: config.fromDate,
      toDate: config.toDate,
      firstDate: snapshots[0]?.date || null,
      lastDate: snapshots.at(-1)?.date || null,
      snapshotCount: snapshots.length,
      indicatorCount: stateFeatureDefs.length,
      observationRows: observationRows.length,
      bucketScheme: bucketDefs.map((bucket) => `${bucket.name}:${bucket.min}-${Math.min(bucket.max, 100)}%`),
      horizons: config.horizons,
      generatedAt: new Date().toISOString()
    },
    summaryRows,
    contrastRows: contrastRows(summaryRows),
    observationRows
  };
}
