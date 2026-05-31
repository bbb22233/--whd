import { buildIndicatorSnapshots } from "./indicators.mjs";

const bucketDefs = [
  { name: "极低", min: 0, max: 10 },
  { name: "偏低", min: 10, max: 30 },
  { name: "中性", min: 30, max: 70 },
  { name: "偏高", min: 70, max: 90 },
  { name: "极高", min: 90, max: 100.000001 }
];

const studyDefs = [
  {
    kindKey: "middle",
    kind: "中值",
    prefix: "中值",
    rateKey: "middleDeviationRate",
    atrKey: "middleDeviationAtr",
    positionKey: "middlePositionPct",
    pickRate: (snapshot) => snapshot.position.middleDeviationRate,
    pickAtr: (snapshot) => snapshot.position.middleDeviationAtr,
    pickPosition: (snapshot) => snapshot.position.middlePositionPct
  },
  {
    kindKey: "ma233",
    kind: "233MA",
    prefix: "233MA",
    rateKey: "maDeviationRate",
    atrKey: "maDeviationAtr",
    positionKey: "maPositionPct",
    pickRate: (snapshot) => snapshot.position.maDeviationRate,
    pickAtr: (snapshot) => snapshot.position.maDeviationAtr,
    pickPosition: (snapshot) => snapshot.position.maPositionPct
  }
];

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

function bucketForRank(rankPct) {
  return bucketDefs.find((bucket) => rankPct >= bucket.min && rankPct < bucket.max) || bucketDefs.at(-1);
}

function bucketOrder(name) {
  return bucketDefs.findIndex((bucket) => bucket.name === name);
}

function prefixMetricRanks(snapshots, metricDef) {
  const uniqueValues = [...new Set(snapshots.map(metricDef.pick).filter(finite))]
    .sort((left, right) => left - right);
  const ranks = new Map(uniqueValues.map((value, index) => [value, index + 1]));
  const tree = Array(uniqueValues.length + 2).fill(0);
  const rows = [];
  let total = 0;

  function add(index, value) {
    for (let cursor = index; cursor < tree.length; cursor += cursor & -cursor) {
      tree[cursor] += value;
    }
  }

  function sum(index) {
    let totalAtIndex = 0;
    for (let cursor = index; cursor > 0; cursor -= cursor & -cursor) {
      totalAtIndex += tree[cursor];
    }
    return totalAtIndex;
  }

  for (const snapshot of snapshots) {
    const value = metricDef.pick(snapshot);
    if (!finite(value)) continue;

    const rank = ranks.get(value);
    add(rank, 1);
    total += 1;

    const less = sum(rank - 1);
    const equal = sum(rank) - less;
    rows.push({
      snapshot,
      value,
      rankPct: ((less + (equal * 0.5)) / total) * 100
    });
  }

  return rows;
}

function classifyDeviation(deviationAtr, positionPct, prefix) {
  const absDeviation = Math.abs(deviationAtr);

  if (absDeviation <= 0.35) {
    return {
      state: `${prefix}贴近中轴`,
      side: 0,
      extremity: "near"
    };
  }

  if (deviationAtr > 0) {
    const extreme = positionPct >= 85 || absDeviation >= 2.5;
    return {
      state: extreme ? `${prefix}上侧极端` : `${prefix}上侧偏离`,
      side: 1,
      extremity: extreme ? "extreme" : "deviation"
    };
  }

  const extreme = positionPct <= 15 || absDeviation >= 2.5;
  return {
    state: extreme ? `${prefix}下侧极端` : `${prefix}下侧偏离`,
    side: -1,
    extremity: extreme ? "extreme" : "deviation"
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

function futureStudyStats(snapshot, futureSnapshot, candles, def, horizon) {
  const priceStats = futurePriceStats(candles, snapshot.index, horizon);
  if (!priceStats) return null;

  const currentAtr = def.pickAtr(snapshot);
  const futureAtr = def.pickAtr(futureSnapshot);
  const currentAbs = Math.abs(currentAtr);
  const futureAbs = Math.abs(futureAtr);
  const side = currentAtr > 0 ? 1 : currentAtr < 0 ? -1 : 0;
  const futureReturnPct = priceStats.futureReturnPct;
  const atrChangePct = safeDivide(
    futureSnapshot.volatility.atrPct - snapshot.volatility.atrPct,
    snapshot.volatility.atrPct
  ) * 100;

  return {
    futureDeviationAtr: futureAtr,
    futureAbsDeviationAtr: futureAbs,
    distanceChangeAtr: futureAbs - currentAbs,
    returnCloser: futureAbs < currentAbs,
    continueAway: futureAbs > currentAbs,
    crossBaseline: side !== 0 && futureAtr * side < 0,
    reversionDirectionHit: side > 0 ? futureReturnPct < 0 : side < 0 ? futureReturnPct > 0 : false,
    continuationDirectionHit: side > 0 ? futureReturnPct > 0 : side < 0 ? futureReturnPct < 0 : false,
    atrChangePct,
    atrUp: atrChangePct > 0,
    atrDown: atrChangePct < 0,
    strongAtrUp: atrChangePct >= 10,
    strongAtrDown: atrChangePct <= -10,
    ...priceStats
  };
}

function stateObservationRow(snapshot, futureSnapshot, candles, def, horizon) {
  const stats = futureStudyStats(snapshot, futureSnapshot, candles, def, horizon);
  if (!stats) return null;

  const deviationRate = def.pickRate(snapshot);
  const deviationAtr = def.pickAtr(snapshot);
  const positionPct = def.pickPosition(snapshot);
  const label = classifyDeviation(deviationAtr, positionPct, def.prefix);

  return {
    date: snapshot.date,
    kind: def.kind,
    kindKey: def.kindKey,
    state: label.state,
    side: label.side,
    extremity: label.extremity,
    horizon,
    close: round(snapshot.price.last, 2),
    deviationRate: round(deviationRate),
    deviationAtr: round(deviationAtr),
    positionPct: round(positionPct, 2),
    futureDeviationAtr: round(stats.futureDeviationAtr),
    distanceChangeAtr: round(stats.distanceChangeAtr),
    returnCloser: stats.returnCloser ? 1 : 0,
    continueAway: stats.continueAway ? 1 : 0,
    crossBaseline: stats.crossBaseline ? 1 : 0,
    reversionDirectionHit: stats.reversionDirectionHit ? 1 : 0,
    continuationDirectionHit: stats.continuationDirectionHit ? 1 : 0,
    atrUp: stats.atrUp ? 1 : 0,
    atrDown: stats.atrDown ? 1 : 0,
    strongAtrUp: stats.strongAtrUp ? 1 : 0,
    strongAtrDown: stats.strongAtrDown ? 1 : 0,
    atrChangePct: round(stats.atrChangePct),
    futureReturnPct: round(stats.futureReturnPct),
    maxUpPct: round(stats.maxUpPct),
    maxDownPct: round(stats.maxDownPct)
  };
}

function metricDefsFor(def) {
  return [
    {
      kind: def.kind,
      kindKey: def.kindKey,
      metricKey: def.rateKey,
      metric: `${def.kind}乖离率`,
      unit: "%",
      pick: def.pickRate
    },
    {
      kind: def.kind,
      kindKey: def.kindKey,
      metricKey: def.atrKey,
      metric: `${def.kind}乖离ATR`,
      unit: "ATR",
      pick: def.pickAtr
    },
    {
      kind: def.kind,
      kindKey: def.kindKey,
      metricKey: def.positionKey,
      metric: `${def.kind}位置百分位`,
      unit: "percentile",
      pick: def.pickPosition
    }
  ];
}

function rankRowsByMetric(snapshots, def, metricDef) {
  return prefixMetricRanks(snapshots, metricDef).map((row) => {
    const bucket = bucketForRank(row.rankPct);
    const deviationAtr = def.pickAtr(row.snapshot);
    const positionPct = def.pickPosition(row.snapshot);
    const stateInfo = classifyDeviation(deviationAtr, positionPct, def.prefix);

    return {
      ...row,
      rankPct: row.rankPct,
      bucket: bucket.name,
      bucketRange: `${bucket.min}-${Math.min(bucket.max, 100)}%`,
      stateInfo
    };
  });
}

function metricObservationRows(snapshots, byIndex, candles, config) {
  return studyDefs.flatMap((def) =>
    metricDefsFor(def).flatMap((metricDef) =>
      rankRowsByMetric(snapshots, def, metricDef).flatMap((ranked) =>
        config.horizons.flatMap((horizon) => {
          const futureSnapshot = byIndex.get(ranked.snapshot.index + horizon);
          if (!futureSnapshot) return [];
          const stats = futureStudyStats(ranked.snapshot, futureSnapshot, candles, def, horizon);
          if (!stats) return [];

          return [{
            date: ranked.snapshot.date,
            kind: metricDef.kind,
            kindKey: metricDef.kindKey,
            metric: metricDef.metric,
            metricKey: metricDef.metricKey,
            unit: metricDef.unit,
            value: round(ranked.value),
            rankPct: round(ranked.rankPct, 2),
            bucket: ranked.bucket,
            bucketRange: ranked.bucketRange,
            state: ranked.stateInfo.state,
            horizon,
            close: round(ranked.snapshot.price.last, 2),
            returnCloser: stats.returnCloser ? 1 : 0,
            continueAway: stats.continueAway ? 1 : 0,
            crossBaseline: stats.crossBaseline ? 1 : 0,
            reversionDirectionHit: stats.reversionDirectionHit ? 1 : 0,
            continuationDirectionHit: stats.continuationDirectionHit ? 1 : 0,
            atrUp: stats.atrUp ? 1 : 0,
            atrDown: stats.atrDown ? 1 : 0,
            strongAtrUp: stats.strongAtrUp ? 1 : 0,
            strongAtrDown: stats.strongAtrDown ? 1 : 0,
            atrChangePct: round(stats.atrChangePct),
            distanceChangeAtr: round(stats.distanceChangeAtr),
            futureReturnPct: round(stats.futureReturnPct),
            maxUpPct: round(stats.maxUpPct),
            maxDownPct: round(stats.maxDownPct)
          }];
        })
      )
    )
  );
}

function summarizeRows(rows, keyFields, extraFields = {}) {
  const groups = new Map();

  for (const row of rows) {
    const key = keyFields.map((field) => row[field]).join("::");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }

  return Array.from(groups.values()).map((groupRows) => {
    const first = groupRows[0];
    const returns = groupRows.map((row) => row.futureReturnPct);
    const distances = groupRows.map((row) => row.distanceChangeAtr);
    const atrChanges = groupRows.map((row) => row.atrChangePct);
    const maxUps = groupRows.map((row) => row.maxUpPct);
    const maxDowns = groupRows.map((row) => row.maxDownPct);
    const base = Object.fromEntries(keyFields.map((field) => [field, first[field]]));

    return {
      ...base,
      ...Object.fromEntries(Object.entries(extraFields).map(([key, pick]) => [key, pick(first, groupRows)])),
      occurrences: groupRows.length,
      returnCloserProbabilityPct: round(safeDivide(groupRows.filter((row) => row.returnCloser === 1).length, groupRows.length) * 100, 2),
      continueAwayProbabilityPct: round(safeDivide(groupRows.filter((row) => row.continueAway === 1).length, groupRows.length) * 100, 2),
      crossBaselineProbabilityPct: round(safeDivide(groupRows.filter((row) => row.crossBaseline === 1).length, groupRows.length) * 100, 2),
      reversionDirectionHitPct: round(safeDivide(groupRows.filter((row) => row.reversionDirectionHit === 1).length, groupRows.length) * 100, 2),
      continuationDirectionHitPct: round(safeDivide(groupRows.filter((row) => row.continuationDirectionHit === 1).length, groupRows.length) * 100, 2),
      atrUpProbabilityPct: round(safeDivide(groupRows.filter((row) => row.atrUp === 1).length, groupRows.length) * 100, 2),
      atrDownProbabilityPct: round(safeDivide(groupRows.filter((row) => row.atrDown === 1).length, groupRows.length) * 100, 2),
      strongAtrUpProbabilityPct: round(safeDivide(groupRows.filter((row) => row.strongAtrUp === 1).length, groupRows.length) * 100, 2),
      strongAtrDownProbabilityPct: round(safeDivide(groupRows.filter((row) => row.strongAtrDown === 1).length, groupRows.length) * 100, 2),
      avgAtrChangePct: round(average(atrChanges)),
      medianAtrChangePct: round(median(atrChanges)),
      avgDistanceChangeAtr: round(average(distances)),
      medianDistanceChangeAtr: round(median(distances)),
      avgReturnPct: round(average(returns)),
      medianReturnPct: round(median(returns)),
      upRatePct: round(safeDivide(groupRows.filter((row) => row.futureReturnPct > 0).length, groupRows.length) * 100, 2),
      avgMaxUpPct: round(average(maxUps)),
      avgMaxDownPct: round(average(maxDowns)),
      lastSeen: groupRows.at(-1)?.date || ""
    };
  });
}

function summarizeStateRows(rows) {
  return summarizeRows(rows, ["kind", "kindKey", "state", "side", "extremity", "horizon"], {
    medianDeviationRate: (_, groupRows) => round(median(groupRows.map((row) => row.deviationRate))),
    medianDeviationAtr: (_, groupRows) => round(median(groupRows.map((row) => row.deviationAtr))),
    medianPositionPct: (_, groupRows) => round(median(groupRows.map((row) => row.positionPct)), 2)
  }).sort((left, right) =>
    left.kind.localeCompare(right.kind, "zh-CN") ||
    left.horizon - right.horizon ||
    left.side - right.side ||
    left.state.localeCompare(right.state, "zh-CN")
  );
}

function summarizeMetricRows(rows) {
  return summarizeRows(rows, ["kind", "kindKey", "metric", "metricKey", "unit", "bucket", "bucketRange", "horizon"], {
    valueMin: (_, groupRows) => round(Math.min(...groupRows.map((row) => row.value))),
    valueMedian: (_, groupRows) => round(median(groupRows.map((row) => row.value))),
    valueMax: (_, groupRows) => round(Math.max(...groupRows.map((row) => row.value)))
  }).sort((left, right) =>
    left.kind.localeCompare(right.kind, "zh-CN") ||
    left.metric.localeCompare(right.metric, "zh-CN") ||
    left.horizon - right.horizon ||
    bucketOrder(left.bucket) - bucketOrder(right.bucket)
  );
}

function contrastMetricRows(summaryRows) {
  const groups = new Map();

  for (const row of summaryRows) {
    const key = `${row.kindKey}::${row.metricKey}::${row.horizon}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }

  return Array.from(groups.values()).flatMap((rows) => {
    const low = rows.find((row) => row.bucket === "极低");
    const high = rows.find((row) => row.bucket === "极高");
    if (!low || !high) return [];

    return [{
      kind: low.kind,
      kindKey: low.kindKey,
      metric: low.metric,
      metricKey: low.metricKey,
      horizon: low.horizon,
      lowOccurrences: low.occurrences,
      highOccurrences: high.occurrences,
      lowValueMedian: low.valueMedian,
      highValueMedian: high.valueMedian,
      lowReturnCloserProbabilityPct: low.returnCloserProbabilityPct,
      highReturnCloserProbabilityPct: high.returnCloserProbabilityPct,
      highMinusLowReturnCloserPct: round(high.returnCloserProbabilityPct - low.returnCloserProbabilityPct, 2),
      lowContinueAwayProbabilityPct: low.continueAwayProbabilityPct,
      highContinueAwayProbabilityPct: high.continueAwayProbabilityPct,
      highMinusLowContinueAwayPct: round(high.continueAwayProbabilityPct - low.continueAwayProbabilityPct, 2),
      lowAtrUpProbabilityPct: low.atrUpProbabilityPct,
      highAtrUpProbabilityPct: high.atrUpProbabilityPct,
      highMinusLowAtrUpPct: round(high.atrUpProbabilityPct - low.atrUpProbabilityPct, 2),
      lowAvgReturnPct: low.avgReturnPct,
      highAvgReturnPct: high.avgReturnPct,
      highMinusLowReturnPct: round(high.avgReturnPct - low.avgReturnPct)
    }];
  }).sort((left, right) =>
    left.kind.localeCompare(right.kind, "zh-CN") ||
    left.metric.localeCompare(right.metric, "zh-CN") ||
    left.horizon - right.horizon
  );
}

function percentileRank(value, values) {
  const valid = values.filter(finite);
  if (!valid.length) return 50;
  const less = valid.filter((item) => item < value).length;
  const equal = valid.filter((item) => item === value).length;
  return ((less + (equal * 0.5)) / valid.length) * 100;
}

function currentRows(selected, stateSummaryRows, horizons) {
  const latest = selected.at(-1);
  if (!latest) return [];
  const stateByKey = new Map(stateSummaryRows.map((row) => [
    `${row.kindKey}::${row.state}::${row.horizon}`,
    row
  ]));

  return studyDefs.flatMap((def) => {
    const deviationRate = def.pickRate(latest);
    const deviationAtr = def.pickAtr(latest);
    const positionPct = def.pickPosition(latest);
    const stateInfo = classifyDeviation(deviationAtr, positionPct, def.prefix);
    const historicalRateRankPct = percentileRank(deviationRate, selected.map(def.pickRate));
    const historicalAtrRankPct = percentileRank(deviationAtr, selected.map(def.pickAtr));
    const historicalPositionRankPct = percentileRank(positionPct, selected.map(def.pickPosition));

    return horizons.map((horizon) => {
      const summary = stateByKey.get(`${def.kindKey}::${stateInfo.state}::${horizon}`);

      return {
        date: latest.date,
        close: round(latest.price.last, 2),
        kind: def.kind,
        kindKey: def.kindKey,
        state: stateInfo.state,
        side: stateInfo.side,
        extremity: stateInfo.extremity,
        deviationRate: round(deviationRate),
        deviationAtr: round(deviationAtr),
        positionPct: round(positionPct, 2),
        historicalRateRankPct: round(historicalRateRankPct, 2),
        historicalAtrRankPct: round(historicalAtrRankPct, 2),
        historicalPositionRankPct: round(historicalPositionRankPct, 2),
        horizon,
        similarOccurrences: summary?.occurrences || 0,
        returnCloserProbabilityPct: summary?.returnCloserProbabilityPct ?? "",
        continueAwayProbabilityPct: summary?.continueAwayProbabilityPct ?? "",
        crossBaselineProbabilityPct: summary?.crossBaselineProbabilityPct ?? "",
        reversionDirectionHitPct: summary?.reversionDirectionHitPct ?? "",
        atrUpProbabilityPct: summary?.atrUpProbabilityPct ?? "",
        atrDownProbabilityPct: summary?.atrDownProbabilityPct ?? "",
        avgAtrChangePct: summary?.avgAtrChangePct ?? "",
        medianDistanceChangeAtr: summary?.medianDistanceChangeAtr ?? ""
      };
    });
  });
}

export function runDeviationStudyFromSnapshots(cleanPayload, config, snapshots) {
  const selected = snapshots.filter((snapshot) => inWindow(snapshot.date, config));
  const byIndex = new Map(snapshots.map((snapshot) => [snapshot.index, snapshot]));
  const stateObservationRows = selected.flatMap((snapshot) =>
    studyDefs.flatMap((def) =>
      config.horizons.flatMap((horizon) => {
        const futureSnapshot = byIndex.get(snapshot.index + horizon);
        if (!futureSnapshot) return [];
        const row = stateObservationRow(snapshot, futureSnapshot, cleanPayload.candles, def, horizon);
        return row ? [row] : [];
      })
    )
  );
  const metricRows = metricObservationRows(selected, byIndex, cleanPayload.candles, config);
  const stateSummaryRows = summarizeStateRows(stateObservationRows);
  const metricSummaryRows = summarizeMetricRows(metricRows);

  return {
    metadata: {
      instrument: cleanPayload.metadata.instrument,
      bar: cleanPayload.metadata.bar,
      fromDate: config.fromDate,
      toDate: config.toDate,
      firstDate: selected[0]?.date || null,
      lastDate: selected.at(-1)?.date || null,
      snapshotCount: selected.length,
      stateObservationRows: stateObservationRows.length,
      metricObservationRows: metricRows.length,
      horizons: config.horizons,
      bucketScheme: bucketDefs.map((bucket) => `${bucket.name}:${bucket.min}-${Math.min(bucket.max, 100)}%`),
      metricBucketMode: "causal_prefix_percentile",
      generatedAt: new Date().toISOString()
    },
    currentRows: currentRows(selected, stateSummaryRows, config.horizons),
    stateSummaryRows,
    metricSummaryRows,
    metricContrastRows: contrastMetricRows(metricSummaryRows),
    stateObservationRows,
    metricObservationRows: metricRows
  };
}

export function runDeviationStudy(cleanPayload, config) {
  return runDeviationStudyFromSnapshots(
    cleanPayload,
    config,
    buildIndicatorSnapshots(cleanPayload.candles, config)
  );
}
