import { buildIndicatorSnapshots } from "./indicators.mjs";

function finite(value) {
  return Number.isFinite(value);
}

function safeDivide(numerator, denominator) {
  if (!finite(numerator) || !finite(denominator) || denominator === 0) return 0;
  return numerator / denominator;
}

function round(value, digits = 4) {
  if (!finite(value)) return 0;
  return Number(value.toFixed(digits));
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

function inWindow(date, config) {
  if (config.fromDate && date < config.fromDate) return false;
  if (config.toDate && date > config.toDate) return false;
  return true;
}

function classifySide(deviationAtr, positionPct, prefix) {
  const absDeviation = Math.abs(deviationAtr);

  if (absDeviation <= 0.35) {
    return {
      label: `${prefix}贴近`,
      side: 0,
      extremity: "near"
    };
  }

  if (deviationAtr > 0) {
    return {
      label: positionPct >= 85 || absDeviation >= 2.5 ? `${prefix}上侧极端` : `${prefix}上侧偏离`,
      side: 1,
      extremity: positionPct >= 85 || absDeviation >= 2.5 ? "extreme" : "deviation"
    };
  }

  return {
    label: positionPct <= 15 || absDeviation >= 2.5 ? `${prefix}下侧极端` : `${prefix}下侧偏离`,
    side: -1,
    extremity: positionPct <= 15 || absDeviation >= 2.5 ? "extreme" : "deviation"
  };
}

function futurePositionStats(snapshot, futureSnapshot, kind) {
  const current = kind === "middle" ? snapshot.position.middleDeviationAtr : snapshot.position.maDeviationAtr;
  const future = kind === "middle" ? futureSnapshot.position.middleDeviationAtr : futureSnapshot.position.maDeviationAtr;
  const currentAbs = Math.abs(current);
  const futureAbs = Math.abs(future);
  const side = current > 0 ? 1 : current < 0 ? -1 : 0;

  return {
    futureDeviationAtr: future,
    futureAbsDeviationAtr: futureAbs,
    returnedCloser: futureAbs < currentAbs,
    continuedAway: futureAbs > currentAbs,
    crossedBaseline: side !== 0 && future * side < 0,
    distanceChangeAtr: futureAbs - currentAbs
  };
}

function futurePriceStats(candles, index, horizon) {
  const entry = candles[index];
  const future = candles.slice(index + 1, index + 1 + horizon);
  if (!entry || future.length < horizon) return null;

  const exit = future.at(-1);
  const maxHigh = Math.max(...future.map((candle) => candle.high));
  const minLow = Math.min(...future.map((candle) => candle.low));

  return {
    futureReturnPct: safeDivide(exit.close - entry.close, entry.close) * 100,
    maxUpPct: safeDivide(maxHigh - entry.close, entry.close) * 100,
    maxDownPct: safeDivide(minLow - entry.close, entry.close) * 100
  };
}

function rowFor(snapshot, futureSnapshot, candles, labelInfo, kind, horizon) {
  const priceStats = futurePriceStats(candles, snapshot.index, horizon);
  if (!priceStats) return null;

  const positionStats = futurePositionStats(snapshot, futureSnapshot, kind);
  const isMiddle = kind === "middle";

  return {
    date: snapshot.date,
    kind: isMiddle ? "中值" : "233MA",
    label: labelInfo.label,
    side: labelInfo.side,
    extremity: labelInfo.extremity,
    horizon,
    close: round(snapshot.price.last, 2),
    deviationRate: round(isMiddle ? snapshot.position.middleDeviationRate : snapshot.position.maDeviationRate),
    deviationAtr: round(isMiddle ? snapshot.position.middleDeviationAtr : snapshot.position.maDeviationAtr),
    positionPct: round(isMiddle ? snapshot.position.middlePositionPct : snapshot.position.maPositionPct, 2),
    futureDeviationAtr: round(positionStats.futureDeviationAtr),
    distanceChangeAtr: round(positionStats.distanceChangeAtr),
    returnCloser: positionStats.returnedCloser ? 1 : 0,
    continueAway: positionStats.continuedAway ? 1 : 0,
    crossBaseline: positionStats.crossedBaseline ? 1 : 0,
    futureReturnPct: round(priceStats.futureReturnPct),
    maxUpPct: round(priceStats.maxUpPct),
    maxDownPct: round(priceStats.maxDownPct)
  };
}

function summarize(rows) {
  const groups = new Map();

  for (const row of rows) {
    const key = `${row.kind}::${row.label}::${row.horizon}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }

  return Array.from(groups.values()).map((groupRows) => {
    const first = groupRows[0];
    const returns = groupRows.map((row) => row.futureReturnPct);
    const distanceChanges = groupRows.map((row) => row.distanceChangeAtr);

    return {
      kind: first.kind,
      label: first.label,
      horizon: first.horizon,
      occurrences: groupRows.length,
      medianDeviationAtr: round(median(groupRows.map((row) => row.deviationAtr))),
      medianPositionPct: round(median(groupRows.map((row) => row.positionPct)), 2),
      returnCloserProbabilityPct: round(safeDivide(groupRows.filter((row) => row.returnCloser === 1).length, groupRows.length) * 100, 2),
      continueAwayProbabilityPct: round(safeDivide(groupRows.filter((row) => row.continueAway === 1).length, groupRows.length) * 100, 2),
      crossBaselineProbabilityPct: round(safeDivide(groupRows.filter((row) => row.crossBaseline === 1).length, groupRows.length) * 100, 2),
      avgDistanceChangeAtr: round(average(distanceChanges)),
      medianDistanceChangeAtr: round(median(distanceChanges)),
      avgReturnPct: round(average(returns)),
      medianReturnPct: round(median(returns)),
      upRatePct: round(safeDivide(groupRows.filter((row) => row.futureReturnPct > 0).length, groupRows.length) * 100, 2),
      avgMaxUpPct: round(average(groupRows.map((row) => row.maxUpPct))),
      avgMaxDownPct: round(average(groupRows.map((row) => row.maxDownPct))),
      lastSeen: groupRows.at(-1)?.date || ""
    };
  }).sort((left, right) =>
    left.kind.localeCompare(right.kind, "zh-CN") ||
    left.label.localeCompare(right.label, "zh-CN") ||
    left.horizon - right.horizon
  );
}

export function runPositionStateBacktest(cleanPayload, config) {
  const snapshots = buildIndicatorSnapshots(cleanPayload.candles, config);
  const selected = snapshots.filter((snapshot) => inWindow(snapshot.date, config));
  const byIndex = new Map(snapshots.map((snapshot) => [snapshot.index, snapshot]));
  const observationRows = [];

  for (const snapshot of selected) {
    const labels = [
      { kind: "middle", info: classifySide(snapshot.position.middleDeviationAtr, snapshot.position.middlePositionPct, "中值") },
      { kind: "ma", info: classifySide(snapshot.position.maDeviationAtr, snapshot.position.maPositionPct, "MA") }
    ];

    for (const item of labels) {
      for (const horizon of config.horizons) {
        const futureSnapshot = byIndex.get(snapshot.index + horizon);
        if (!futureSnapshot) continue;
        const row = rowFor(snapshot, futureSnapshot, cleanPayload.candles, item.info, item.kind, horizon);
        if (row) observationRows.push(row);
      }
    }
  }

  const latest = selected.at(-1);
  const currentLabels = latest ? [
    classifySide(latest.position.middleDeviationAtr, latest.position.middlePositionPct, "中值"),
    classifySide(latest.position.maDeviationAtr, latest.position.maPositionPct, "MA")
  ] : [];

  return {
    metadata: {
      instrument: cleanPayload.metadata.instrument,
      bar: cleanPayload.metadata.bar,
      fromDate: config.fromDate,
      toDate: config.toDate,
      firstDate: selected[0]?.date || null,
      lastDate: latest?.date || null,
      snapshotCount: selected.length,
      observationRows: observationRows.length,
      horizons: config.horizons,
      generatedAt: new Date().toISOString(),
      current: latest ? {
        date: latest.date,
        middleDeviationRate: round(latest.position.middleDeviationRate),
        middleDeviationAtr: round(latest.position.middleDeviationAtr),
        middlePositionPct: round(latest.position.middlePositionPct, 2),
        maDeviationRate: round(latest.position.maDeviationRate),
        maDeviationAtr: round(latest.position.maDeviationAtr),
        maPositionPct: round(latest.position.maPositionPct, 2),
        labels: currentLabels.map((label) => label.label)
      } : null
    },
    summaryRows: summarize(observationRows),
    observationRows
  };
}
