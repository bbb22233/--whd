import { buildWeatherLabels } from "./feature-factory.mjs";
import { buildIndicatorSnapshots } from "./indicators.mjs";
import { routeStrategies } from "./strategy-router.mjs";

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

function scoreBucket(score) {
  if (score >= 70) return "高适配";
  if (score >= 50) return "中适配";
  if (score >= 30) return "低适配";
  return "不适配";
}

function bucketOrder(bucket) {
  return ["不适配", "低适配", "中适配", "高适配"].indexOf(bucket);
}

function futurePriceStats(candles, index, horizon) {
  const entry = candles[index];
  const future = candles.slice(index + 1, index + 1 + horizon);
  if (!entry || future.length < horizon) return null;

  const exit = future.at(-1);
  const maxHigh = Math.max(...future.map((candle) => candle.high));
  const minLow = Math.min(...future.map((candle) => candle.low));
  const maxUpPct = safeDivide(maxHigh - entry.close, entry.close) * 100;
  const maxDownPct = safeDivide(minLow - entry.close, entry.close) * 100;

  return {
    futureReturnPct: safeDivide(exit.close - entry.close, entry.close) * 100,
    maxUpPct,
    maxDownPct,
    absReturnPct: Math.abs(safeDivide(exit.close - entry.close, entry.close) * 100),
    futureRangePct: maxUpPct - maxDownPct
  };
}

function positionFutureStats(snapshot, futureSnapshot) {
  const current = snapshot.position.middleDeviationAtr;
  const future = futureSnapshot.position.middleDeviationAtr;
  const currentAbs = Math.abs(current);
  const futureAbs = Math.abs(future);
  const side = current > 0 ? 1 : current < 0 ? -1 : 0;

  return {
    returnedCloser: futureAbs < currentAbs,
    continuedAway: futureAbs > currentAbs,
    crossedMiddle: side !== 0 && future * side < 0,
    distanceChangeAtr: futureAbs - currentAbs
  };
}

function routeOutcome(route, snapshot, futureSnapshot, priceStats, horizon) {
  const targetMovePct = Math.max(snapshot.volatility.atrPct, 0.5);
  const positionStats = positionFutureStats(snapshot, futureSnapshot);
  const allowedGridDrift = targetMovePct * Math.sqrt(Math.max(1, horizon));
  const allowedGridRange = targetMovePct * 1.65 * Math.sqrt(Math.max(1, horizon));

  if (route.key === "trendLong") {
    return {
      success: priceStats.futureReturnPct > 0,
      directionalWin: priceStats.futureReturnPct > 0,
      routeReturnPct: priceStats.futureReturnPct
    };
  }

  if (route.key === "trendShort") {
    return {
      success: priceStats.futureReturnPct < 0,
      directionalWin: priceStats.futureReturnPct < 0,
      routeReturnPct: -priceStats.futureReturnPct
    };
  }

  if (route.key === "breakoutUp") {
    return {
      success: priceStats.maxUpPct >= targetMovePct,
      directionalWin: priceStats.futureReturnPct > 0,
      routeReturnPct: priceStats.maxUpPct
    };
  }

  if (route.key === "breakoutDown") {
    return {
      success: priceStats.maxDownPct <= -targetMovePct,
      directionalWin: priceStats.futureReturnPct < 0,
      routeReturnPct: Math.abs(priceStats.maxDownPct)
    };
  }

  if (route.key === "meanReversionLong") {
    return {
      success: snapshot.position.middleDeviationAtr < 0 && positionStats.returnedCloser,
      directionalWin: priceStats.futureReturnPct > 0,
      routeReturnPct: priceStats.futureReturnPct
    };
  }

  if (route.key === "meanReversionShort") {
    return {
      success: snapshot.position.middleDeviationAtr > 0 && positionStats.returnedCloser,
      directionalWin: priceStats.futureReturnPct < 0,
      routeReturnPct: -priceStats.futureReturnPct
    };
  }

  if (route.key === "gridNeutral") {
    const closeToFlat = Math.abs(priceStats.futureReturnPct) <= allowedGridDrift;
    const notExplosive = priceStats.futureRangePct <= allowedGridRange;
    return {
      success: closeToFlat && notExplosive,
      directionalWin: null,
      routeReturnPct: -Math.abs(priceStats.futureReturnPct)
    };
  }

  if (route.key === "waitDefense") {
    const avoidedWeakLong = priceStats.futureReturnPct <= 0 || priceStats.maxDownPct <= -targetMovePct;
    return {
      success: avoidedWeakLong,
      directionalWin: null,
      routeReturnPct: Math.max(0, -priceStats.futureReturnPct)
    };
  }

  return {
    success: false,
    directionalWin: null,
    routeReturnPct: 0
  };
}

function observationRow(route, snapshot, labels, priceStats, outcome, horizon) {
  return {
    date: snapshot.date,
    routeKey: route.key,
    routeLabel: route.label,
    family: route.family,
    direction: route.direction,
    score: route.score,
    scoreBucket: scoreBucket(route.score),
    horizon,
    close: round(snapshot.price.last, 2),
    weatherLabels: labels.map((label) => `${label.dimension}:${label.label}`).join(" | "),
    reasons: route.reasons.join(" | "),
    success: outcome.success ? 1 : 0,
    directionalWin: outcome.directionalWin === null ? "" : outcome.directionalWin ? 1 : 0,
    routeReturnPct: round(outcome.routeReturnPct),
    futureReturnPct: round(priceStats.futureReturnPct),
    absReturnPct: round(priceStats.absReturnPct),
    maxUpPct: round(priceStats.maxUpPct),
    maxDownPct: round(priceStats.maxDownPct),
    futureRangePct: round(priceStats.futureRangePct),
    atrPct: round(snapshot.volatility.atrPct),
    volatilityMultiple: round(snapshot.volatility.multiple),
    atr3To21: round(snapshot.volatility.fibAtrComparisons.atr3To21),
    volumeMultiple: round(snapshot.volume.multiple),
    trendScore: round(snapshot.momentum.trendScore),
    middleDeviationAtr: round(snapshot.position.middleDeviationAtr),
    maDeviationAtr: round(snapshot.position.maDeviationAtr)
  };
}

function summarize(rows) {
  const groups = new Map();

  for (const row of rows) {
    const key = `${row.routeKey}::${row.scoreBucket}::${row.horizon}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }

  return Array.from(groups.values()).map((groupRows) => {
    const first = groupRows[0];
    const routeReturns = groupRows.map((row) => row.routeReturnPct);
    const directionalRows = groupRows.filter((row) => row.directionalWin !== "");

    return {
      routeKey: first.routeKey,
      routeLabel: first.routeLabel,
      family: first.family,
      direction: first.direction,
      scoreBucket: first.scoreBucket,
      horizon: first.horizon,
      occurrences: groupRows.length,
      avgScore: round(average(groupRows.map((row) => row.score)), 2),
      medianScore: round(median(groupRows.map((row) => row.score)), 2),
      successRatePct: round(safeDivide(groupRows.filter((row) => row.success === 1).length, groupRows.length) * 100, 2),
      directionalWinRatePct: directionalRows.length
        ? round(safeDivide(directionalRows.filter((row) => row.directionalWin === 1).length, directionalRows.length) * 100, 2)
        : "",
      avgRouteReturnPct: round(average(routeReturns)),
      medianRouteReturnPct: round(median(routeReturns)),
      avgFutureReturnPct: round(average(groupRows.map((row) => row.futureReturnPct))),
      avgAbsReturnPct: round(average(groupRows.map((row) => row.absReturnPct))),
      avgMaxUpPct: round(average(groupRows.map((row) => row.maxUpPct))),
      avgMaxDownPct: round(average(groupRows.map((row) => row.maxDownPct))),
      lastSeen: groupRows.at(-1)?.date || ""
    };
  }).sort((left, right) =>
    left.routeKey.localeCompare(right.routeKey) ||
    left.horizon - right.horizon ||
    bucketOrder(left.scoreBucket) - bucketOrder(right.scoreBucket)
  );
}

export function runStrategyRouterBacktest(cleanPayload, config, snapshots = null) {
  const builtSnapshots = snapshots ?? buildIndicatorSnapshots(cleanPayload.candles, config);
  const selected = builtSnapshots.filter((snapshot) => inWindow(snapshot.date, config));
  const byIndex = new Map(builtSnapshots.map((snapshot) => [snapshot.index, snapshot]));
  const observationRows = [];
  let current = null;

  for (const snapshot of selected) {
    const labels = buildWeatherLabels(snapshot, config);
    const routeResult = routeStrategies(snapshot, labels);

    current = {
      date: snapshot.date,
      close: round(snapshot.price.last, 2),
      labels,
      scores: routeResult.scores,
      topRoutes: routeResult.topRoutes
    };

    for (const route of routeResult.routes) {
      for (const horizon of config.horizons) {
        const futureSnapshot = byIndex.get(snapshot.index + horizon);
        if (!futureSnapshot) continue;
        const priceStats = futurePriceStats(cleanPayload.candles, snapshot.index, horizon);
        if (!priceStats) continue;
        const outcome = routeOutcome(route, snapshot, futureSnapshot, priceStats, horizon);
        observationRows.push(observationRow(route, snapshot, labels, priceStats, outcome, horizon));
      }
    }
  }

  return {
    metadata: {
      instrument: cleanPayload.metadata.instrument,
      bar: cleanPayload.metadata.bar,
      fromDate: config.fromDate,
      toDate: config.toDate,
      firstDate: selected[0]?.date || null,
      lastDate: selected.at(-1)?.date || null,
      snapshotCount: selected.length,
      routeCount: 8,
      observationRows: observationRows.length,
      horizons: config.horizons,
      generatedAt: new Date().toISOString(),
      current
    },
    summaryRows: summarize(observationRows),
    observationRows
  };
}
