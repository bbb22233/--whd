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

export function classifyVolatilityState(snapshot) {
  const atrPercentile = snapshot.volatility.atrPercentile;
  const multiplePercentile = snapshot.volatility.multiplePercentile;
  const candidates = [
    {
      state: "波动压缩",
      confidence: Math.max(0, ((35 - atrPercentile) / 35) + ((35 - multiplePercentile) / 35)) / 2
    },
    {
      state: "波动启动",
      confidence: Math.max(0, ((45 - atrPercentile) / 45) + ((multiplePercentile - 70) / 30)) / 2
    },
    {
      state: "高波动扩张",
      confidence: Math.max(0, ((atrPercentile - 65) / 35) + ((multiplePercentile - 65) / 35)) / 2
    },
    {
      state: "高波动冷却",
      confidence: Math.max(0, ((atrPercentile - 65) / 35) + ((35 - multiplePercentile) / 35)) / 2
    }
  ].sort((left, right) => right.confidence - left.confidence);

  if (candidates[0].confidence <= 0.05) {
    const middleDistance = (Math.abs(atrPercentile - 50) + Math.abs(multiplePercentile - 50)) / 100;
    return {
      state: "常态波动",
      confidence: Math.max(0, Math.min(1, 1 - middleDistance))
    };
  }

  return {
    state: candidates[0].state,
    confidence: Math.max(0, Math.min(1, candidates[0].confidence))
  };
}

function futureStats(snapshot, futureSnapshot) {
  const atrChangePct = safeDivide(
    futureSnapshot.volatility.atrPct - snapshot.volatility.atrPct,
    snapshot.volatility.atrPct
  ) * 100;
  const multipleChange = futureSnapshot.volatility.multiple - snapshot.volatility.multiple;

  return {
    atrChangePct,
    atrUp: atrChangePct > 0,
    atrDown: atrChangePct < 0,
    futureMultiple: futureSnapshot.volatility.multiple,
    futureRemainingMomentumAtr: futureSnapshot.volatility.remainingMomentumAtr,
    futureRemainingMomentumPositive: futureSnapshot.volatility.remainingMomentumAtr > 0,
    multipleChange
  };
}

function observationRows(snapshots, config) {
  const byIndex = new Map(snapshots.map((snapshot) => [snapshot.index, snapshot]));
  const selected = snapshots.filter((snapshot) => inWindow(snapshot.date, config));
  return selected.flatMap((snapshot) => {
    const state = classifyVolatilityState(snapshot);

    return config.horizons.flatMap((horizon) => {
      const futureSnapshot = byIndex.get(snapshot.index + horizon);
      if (!futureSnapshot) return [];
      const future = futureStats(snapshot, futureSnapshot);

      return [{
        date: snapshot.date,
        state: state.state,
        confidence: round(state.confidence, 4),
        horizon,
        atrPct: round(snapshot.volatility.atrPct),
        atrPercentile: round(snapshot.volatility.atrPercentile, 2),
        volatilityMultiple: round(snapshot.volatility.multiple),
        volatilityMultiplePercentile: round(snapshot.volatility.multiplePercentile, 2),
        remainingMomentumPct: round(snapshot.volatility.remainingMomentumPct),
        remainingMomentumAtr: round(snapshot.volatility.remainingMomentumAtr),
        atrChangePct: round(future.atrChangePct),
        atrDirection: future.atrUp ? "up" : future.atrDown ? "down" : "flat",
        futureVolatilityMultiple: round(future.futureMultiple),
        futureRemainingMomentumAtr: round(future.futureRemainingMomentumAtr),
        futureRemainingMomentumPositive: future.futureRemainingMomentumPositive ? 1 : 0,
        multipleChange: round(future.multipleChange)
      }];
    });
  });
}

function summarize(rows) {
  const groups = new Map();

  for (const row of rows) {
    const key = `${row.state}::${row.horizon}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }

  return Array.from(groups.values()).map((groupRows) => {
    const first = groupRows[0];
    const atrChanges = groupRows.map((row) => row.atrChangePct);
    const momentumAtr = groupRows.map((row) => row.remainingMomentumAtr);

    return {
      state: first.state,
      horizon: first.horizon,
      occurrences: groupRows.length,
      avgConfidencePct: round(average(groupRows.map((row) => row.confidence)) * 100, 2),
      avgAtrPercentile: round(average(groupRows.map((row) => row.atrPercentile)), 2),
      avgVolatilityMultiplePercentile: round(average(groupRows.map((row) => row.volatilityMultiplePercentile)), 2),
      avgRemainingMomentumAtr: round(average(momentumAtr)),
      medianRemainingMomentumAtr: round(median(momentumAtr)),
      atrUpProbabilityPct: round(safeDivide(groupRows.filter((row) => row.atrDirection === "up").length, groupRows.length) * 100, 2),
      atrDownProbabilityPct: round(safeDivide(groupRows.filter((row) => row.atrDirection === "down").length, groupRows.length) * 100, 2),
      avgAtrChangePct: round(average(atrChanges)),
      medianAtrChangePct: round(median(atrChanges)),
      futureRemainingMomentumPositivePct: round(safeDivide(groupRows.filter((row) => row.futureRemainingMomentumPositive === 1).length, groupRows.length) * 100, 2),
      avgFutureVolatilityMultiple: round(average(groupRows.map((row) => row.futureVolatilityMultiple))),
      lastSeen: groupRows.at(-1)?.date || ""
    };
  }).sort((left, right) => left.state.localeCompare(right.state, "zh-CN") || left.horizon - right.horizon);
}

export function runVolatilityStateBacktest(cleanPayload, config) {
  const snapshots = buildIndicatorSnapshots(cleanPayload.candles, config);
  const rows = observationRows(snapshots, config);
  const latestSnapshot = snapshots.filter((snapshot) => inWindow(snapshot.date, config)).at(-1);
  const currentState = latestSnapshot ? classifyVolatilityState(latestSnapshot) : null;

  return {
    metadata: {
      instrument: cleanPayload.metadata.instrument,
      bar: cleanPayload.metadata.bar,
      fromDate: config.fromDate,
      toDate: config.toDate,
      firstDate: snapshots.filter((snapshot) => inWindow(snapshot.date, config))[0]?.date || null,
      lastDate: latestSnapshot?.date || null,
      snapshotCount: snapshots.filter((snapshot) => inWindow(snapshot.date, config)).length,
      observationRows: rows.length,
      horizons: config.horizons,
      generatedAt: new Date().toISOString(),
      currentState: latestSnapshot ? {
        date: latestSnapshot.date,
        state: currentState.state,
        confidencePct: round(currentState.confidence * 100, 2),
        atrPct: round(latestSnapshot.volatility.atrPct),
        atrPercentile: round(latestSnapshot.volatility.atrPercentile, 2),
        volatilityMultiple: round(latestSnapshot.volatility.multiple),
        volatilityMultiplePercentile: round(latestSnapshot.volatility.multiplePercentile, 2),
        remainingMomentumPct: round(latestSnapshot.volatility.remainingMomentumPct),
        remainingMomentumAtr: round(latestSnapshot.volatility.remainingMomentumAtr)
      } : null
    },
    summaryRows: summarize(rows),
    observationRows: rows
  };
}
