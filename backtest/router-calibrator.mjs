import { runStrategyRouterBacktest } from "./strategy-router-backtest.mjs";

function finite(value) {
  return Number.isFinite(value);
}

function safeDivide(numerator, denominator) {
  if (!finite(numerator) || !finite(denominator) || denominator === 0) return 0;
  return numerator / denominator;
}

function clamp(value, min, max) {
  if (!finite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function round(value, digits = 2) {
  if (!finite(value)) return 0;
  return Number(value.toFixed(digits));
}

function average(values) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function scoreBucket(score) {
  if (score >= 70) return "高适配";
  if (score >= 50) return "中适配";
  if (score >= 30) return "低适配";
  return "不适配";
}

function routeSignalType(routeKey) {
  if (routeKey.startsWith("trend")) return "方向信号";
  if (routeKey.startsWith("breakout")) return "波动方向信号";
  if (routeKey.startsWith("meanReversion")) return "位置回归信号";
  if (routeKey === "gridNeutral") return "震荡状态信号";
  if (routeKey === "waitDefense") return "风险过滤信号";
  return "状态信号";
}

function trafficLightName(score) {
  if (score >= 68) return "绿灯";
  if (score >= 48) return "黄灯";
  return "红灯";
}

function lightReason(signalType, stats) {
  if (stats.occurrences < 30) return "样本偏少，只能观察";
  if (signalType === "方向信号" && stats.directionalWinRatePct < 50) return "方向胜率不足，不宜当进攻信号";
  if (signalType === "位置回归信号" && stats.successRatePct >= 55 && stats.avgRouteReturnPct <= 0.5) return "能证明位置回归，但不能证明直接开方向仓";
  if (signalType === "风险过滤信号") return "更适合做仓位/入场过滤，不是方向信号";
  if (stats.successLiftPct > 5) return "当前分桶明显好于历史基线";
  if (stats.successLiftPct > 0) return "当前分桶略好于历史基线";
  return "当前分桶没有明显优于历史基线";
}

function statsFor(rows) {
  const directionalRows = rows.filter((row) => row.directionalWin !== "");
  return {
    occurrences: rows.length,
    successRatePct: safeDivide(rows.filter((row) => row.success === 1).length, rows.length) * 100,
    directionalWinRatePct: directionalRows.length
      ? safeDivide(directionalRows.filter((row) => row.directionalWin === 1).length, directionalRows.length) * 100
      : null,
    avgRouteReturnPct: average(rows.map((row) => row.routeReturnPct)),
    avgFutureReturnPct: average(rows.map((row) => row.futureReturnPct)),
    avgAbsReturnPct: average(rows.map((row) => row.absReturnPct))
  };
}

function groupBy(rows, makeKey) {
  const groups = new Map();
  for (const row of rows) {
    const key = makeKey(row);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }
  return groups;
}

function routeMeta(rows) {
  const byKey = new Map();
  for (const row of rows) {
    if (byKey.has(row.routeKey)) continue;
    byKey.set(row.routeKey, {
      routeKey: row.routeKey,
      routeLabel: row.routeLabel,
      family: row.family,
      direction: row.direction,
      signalType: routeSignalType(row.routeKey)
    });
  }
  return byKey;
}

function sampleConfidence(occurrences) {
  return clamp(Math.sqrt(occurrences / 200) * 100, 0, 100);
}

function calibrationScore(meta, currentScore, bucketStats, baselineStats) {
  const successLift = bucketStats.successRatePct - baselineStats.successRatePct;
  const routeReturnLift = bucketStats.avgRouteReturnPct - baselineStats.avgRouteReturnPct;
  const directionalLift = bucketStats.directionalWinRatePct === null || baselineStats.directionalWinRatePct === null
    ? 0
    : bucketStats.directionalWinRatePct - baselineStats.directionalWinRatePct;
  const sample = sampleConfidence(bucketStats.occurrences);
  let score = 42 + (currentScore * 0.22) + (successLift * 1.2) + clamp(routeReturnLift * 3, -18, 18);

  if (meta.signalType.includes("方向")) {
    score += directionalLift * 0.9;
  }

  if (meta.signalType === "位置回归信号" && bucketStats.successRatePct >= 55 && bucketStats.avgRouteReturnPct <= 0.5) {
    score = Math.min(score, 62);
  }

  if (meta.routeKey === "trendShort" && bucketStats.directionalWinRatePct !== null && bucketStats.directionalWinRatePct < 50) {
    score = Math.min(score, 46);
  }

  if (bucketStats.occurrences < 30) {
    score = Math.min(score, 45);
  }

  return clamp(score * (0.65 + (sample / 100 * 0.35)), 0, 100);
}

function buildCalibrationRows(backtestResult) {
  const rows = backtestResult.observationRows;
  const currentScores = backtestResult.metadata.current?.scores || {};
  const metaByRoute = routeMeta(rows);
  const routeHorizonRows = groupBy(rows, (row) => `${row.routeKey}::${row.horizon}`);
  const routeHorizonBucketRows = groupBy(rows, (row) => `${row.routeKey}::${row.horizon}::${row.scoreBucket}`);
  const calibrationRows = [];

  for (const [routeKey, meta] of metaByRoute.entries()) {
    const currentScore = currentScores[routeKey] ?? 0;
    const currentBucket = scoreBucket(currentScore);

    for (const horizon of backtestResult.metadata.horizons) {
      const baseline = statsFor(routeHorizonRows.get(`${routeKey}::${horizon}`) || []);
      const bucket = statsFor(routeHorizonBucketRows.get(`${routeKey}::${horizon}::${currentBucket}`) || []);
      if (!bucket.occurrences || !baseline.occurrences) continue;

      const successLiftPct = bucket.successRatePct - baseline.successRatePct;
      const directionalLiftPct = bucket.directionalWinRatePct === null || baseline.directionalWinRatePct === null
        ? null
        : bucket.directionalWinRatePct - baseline.directionalWinRatePct;
      const routeReturnLiftPct = bucket.avgRouteReturnPct - baseline.avgRouteReturnPct;
      const confidencePct = sampleConfidence(bucket.occurrences);
      const score = calibrationScore(meta, currentScore, bucket, baseline);
      let light = trafficLightName(score);
      if (currentBucket === "不适配") light = "红灯";
      if (meta.signalType === "位置回归信号" && bucket.successRatePct >= 55 && bucket.avgRouteReturnPct <= 0.5 && light === "绿灯") {
        light = "黄灯";
      }
      if (meta.routeKey === "trendShort" && bucket.directionalWinRatePct !== null && bucket.directionalWinRatePct < 50) {
        light = "红灯";
      }

      calibrationRows.push({
        routeKey,
        routeLabel: meta.routeLabel,
        family: meta.family,
        direction: meta.direction,
        signalType: meta.signalType,
        horizon,
        currentScore: round(currentScore),
        currentBucket,
        light,
        calibrationScore: round(score),
        sampleConfidencePct: round(confidencePct),
        occurrences: bucket.occurrences,
        baselineOccurrences: baseline.occurrences,
        successRatePct: round(bucket.successRatePct),
        baselineSuccessRatePct: round(baseline.successRatePct),
        successLiftPct: round(successLiftPct),
        directionalWinRatePct: bucket.directionalWinRatePct === null ? "" : round(bucket.directionalWinRatePct),
        baselineDirectionalWinRatePct: baseline.directionalWinRatePct === null ? "" : round(baseline.directionalWinRatePct),
        directionalLiftPct: directionalLiftPct === null ? "" : round(directionalLiftPct),
        avgRouteReturnPct: round(bucket.avgRouteReturnPct),
        baselineAvgRouteReturnPct: round(baseline.avgRouteReturnPct),
        routeReturnLiftPct: round(routeReturnLiftPct),
        avgFutureReturnPct: round(bucket.avgFutureReturnPct),
        avgAbsReturnPct: round(bucket.avgAbsReturnPct),
        reason: lightReason(meta.signalType, {
          ...bucket,
          successLiftPct,
          directionalLiftPct,
          routeReturnLiftPct
        })
      });
    }
  }

  return calibrationRows.sort((left, right) =>
    right.currentScore - left.currentScore ||
    right.calibrationScore - left.calibrationScore ||
    left.horizon - right.horizon
  );
}

function bestRowForRoute(rows, routeKey) {
  const routeRows = rows.filter((row) => row.routeKey === routeKey);
  if (!routeRows.length) return null;
  return [...routeRows].sort((left, right) =>
    lightRank(right.light) - lightRank(left.light) ||
    right.calibrationScore - left.calibrationScore ||
    right.sampleConfidencePct - left.sampleConfidencePct
  )[0];
}

function lightRank(light) {
  if (light === "绿灯") return 3;
  if (light === "黄灯") return 2;
  if (light === "红灯") return 1;
  return 0;
}

function currentSignals(calibrationRows, backtestResult) {
  const currentScores = backtestResult.metadata.current?.scores || {};
  const routes = Object.keys(currentScores)
    .filter((key) => !["trendFollowing", "breakout", "meanReversion", "grid", "wait"].includes(key))
    .map((routeKey) => bestRowForRoute(calibrationRows, routeKey))
    .filter(Boolean)
    .sort((left, right) => right.currentScore - left.currentScore);

  return routes.map((row) => ({
    routeKey: row.routeKey,
    routeLabel: row.routeLabel,
    light: row.light,
    signalType: row.signalType,
    currentScore: row.currentScore,
    bestHorizon: row.horizon,
    calibrationScore: row.calibrationScore,
    sampleConfidencePct: row.sampleConfidencePct,
    successRatePct: row.successRatePct,
    successLiftPct: row.successLiftPct,
    directionalWinRatePct: row.directionalWinRatePct,
    avgRouteReturnPct: row.avgRouteReturnPct,
    reason: row.reason
  }));
}

export function runRouterCalibration(cleanPayload, config) {
  const backtestResult = runStrategyRouterBacktest(cleanPayload, config);
  const calibrationRows = buildCalibrationRows(backtestResult);
  const signals = currentSignals(calibrationRows, backtestResult);

  return {
    metadata: {
      ...backtestResult.metadata,
      generatedAt: new Date().toISOString(),
      calibration: {
        scoreBuckets: "不适配:<30, 低适配:30-49, 中适配:50-69, 高适配:>=70",
        sampleConfidence: "sqrt(当前分桶样本数 / 200)，最高100%",
        lights: "绿灯=历史校准较强，黄灯=可观察/需确认，红灯=不适合单独开工"
      },
      currentSignals: signals
    },
    calibrationRows,
    observationRows: backtestResult.observationRows,
    summaryRows: backtestResult.summaryRows
  };
}
