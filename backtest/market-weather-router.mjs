import { buildIndicatorSnapshots } from "./indicators.mjs";
import { runDeviationStudyFromSnapshots } from "./deviation-study.mjs";
import { buildDeviationRules } from "./deviation-rules.mjs";
import { buildWeatherLabels } from "./feature-factory.mjs";
import { routeStrategies } from "./strategy-router.mjs";
import { runRouterCalibration } from "./router-calibrator.mjs";

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

function confidenceLabel(samples, edgePct) {
  if (samples < 120) return "样本偏少";
  if (edgePct >= 25) return "强";
  if (edgePct >= 15) return "中强";
  if (edgePct >= 8) return "中";
  return "弱";
}

function classifyVolatility(snapshot) {
  const atrPercentile = snapshot.volatility.atrPercentile;
  const multiplePercentile = snapshot.volatility.multiplePercentile;
  const multiple = snapshot.volatility.multiple;
  const remaining = snapshot.volatility.remainingMomentumAtr;
  const candidates = [
    {
      state: "波动压缩",
      score: ((35 - atrPercentile) / 35) + ((35 - multiplePercentile) / 35)
    },
    {
      state: "低波动启动",
      score: ((45 - atrPercentile) / 45) + ((multiplePercentile - 70) / 30) + (multiple >= 1 ? 0.25 : 0)
    },
    {
      state: "高波动扩张",
      score: ((atrPercentile - 65) / 35) + ((multiplePercentile - 65) / 35) + (remaining > 0 ? 0.2 : 0)
    },
    {
      state: "高波动冷却",
      score: ((atrPercentile - 65) / 35) + ((35 - multiplePercentile) / 35) + (remaining < 0 ? 0.2 : 0)
    }
  ].map((item) => ({ ...item, score: Math.max(0, item.score) }))
    .sort((left, right) => right.score - left.score);

  if (!candidates[0] || candidates[0].score <= 0.1) {
    const middleDistance = (Math.abs(atrPercentile - 50) + Math.abs(multiplePercentile - 50)) / 100;
    return {
      state: "常态波动",
      confidencePct: round(clamp(1 - middleDistance, 0, 1) * 100, 2)
    };
  }

  return {
    state: candidates[0].state,
    confidencePct: round(clamp(candidates[0].score / 2, 0, 1) * 100, 2)
  };
}

function classifyShortAtr(snapshot) {
  const { atr3To21, atr8To21 } = snapshot.volatility.fibAtrComparisons;

  if (atr3To21 >= 1.08 && atr8To21 >= 1) {
    return {
      state: "短ATR升温",
      confidencePct: round(clamp(((atr3To21 - 1) + Math.max(0, atr8To21 - 1)) / 0.35, 0, 1) * 100, 2)
    };
  }

  if (atr3To21 <= 0.88 && atr8To21 <= 0.96) {
    return {
      state: "短ATR降温",
      confidencePct: round(clamp(((1 - atr3To21) + Math.max(0, 1 - atr8To21)) / 0.35, 0, 1) * 100, 2)
    };
  }

  return {
    state: "短ATR中性",
    confidencePct: round(clamp(1 - Math.abs(atr3To21 - 1), 0, 1) * 100, 2)
  };
}

function classifyEnergy(snapshot) {
  const remaining = snapshot.volatility.remainingMomentumAtr;

  if (remaining >= 0.2) {
    return {
      state: "振幅已超ATR",
      confidencePct: round(clamp(remaining / 1.2, 0, 1) * 100, 2)
    };
  }

  if (remaining <= -0.2) {
    return {
      state: "振幅未满ATR",
      confidencePct: round(clamp(Math.abs(remaining) / 1.2, 0, 1) * 100, 2)
    };
  }

  return {
    state: "接近一倍ATR",
    confidencePct: round(clamp(1 - Math.abs(remaining) / 0.2, 0, 1) * 100, 2)
  };
}

function classifyTrend(snapshot, config) {
  const trendScore = snapshot.momentum.trendScore;
  const absTrend = Math.abs(trendScore);
  const direction = snapshot.momentum.resonanceDirection;
  const count = snapshot.momentum.resonanceCount;
  const strongTrendPct = config.thresholds?.strongTrendPct || 3;
  const weakTrendPct = config.thresholds?.weakTrendPct || 1.2;

  if (count >= 3 && absTrend >= strongTrendPct && direction !== "mixed") {
    return {
      state: direction === "up" ? "强趋势上行" : "强趋势下行",
      direction,
      strength: "strong",
      confidencePct: round(clamp((absTrend / (strongTrendPct * 2)) + (count / 8), 0, 1) * 100, 2)
    };
  }

  if (count >= 2 && absTrend >= weakTrendPct) {
    return {
      state: direction === "up" ? "弱趋势上行" : direction === "down" ? "弱趋势下行" : "弱趋势混合",
      direction,
      strength: "weak",
      confidencePct: round(clamp((absTrend / (strongTrendPct * 2)) + (count / 10), 0, 0.75) * 100, 2)
    };
  }

  return {
    state: "趋势不明",
    direction: "mixed",
    strength: "none",
    confidencePct: round(clamp(1 - (absTrend / strongTrendPct), 0, 1) * 100, 2)
  };
}

function classifyVolume(snapshot, config) {
  const multiple = snapshot.volume.multiple;
  const expansion = config.thresholds?.volumeExpansion || 1.5;

  if (multiple >= expansion) {
    return {
      state: "放量",
      confidencePct: round(clamp((multiple - expansion) / expansion, 0, 1) * 100, 2)
    };
  }

  if (multiple <= 0.75) {
    return {
      state: "缩量",
      confidencePct: round(clamp((0.75 - multiple) / 0.75, 0, 1) * 100, 2)
    };
  }

  return {
    state: "量能正常",
    confidencePct: round(clamp(1 - Math.abs(multiple - 1), 0, 1) * 100, 2)
  };
}

function futureVolatilityStats(snapshot, futureSnapshot) {
  const atrChangePct = safeDivide(
    futureSnapshot.volatility.atrPct - snapshot.volatility.atrPct,
    snapshot.volatility.atrPct
  ) * 100;
  const multipleChange = futureSnapshot.volatility.multiple - snapshot.volatility.multiple;

  return {
    atrChangePct,
    atrDirection: atrChangePct > 0 ? "up" : atrChangePct < 0 ? "down" : "flat",
    strongAtrUp: atrChangePct >= 10,
    strongAtrDown: atrChangePct <= -10,
    futureVolatilityMultiple: futureSnapshot.volatility.multiple,
    futureRemainingMomentumAtr: futureSnapshot.volatility.remainingMomentumAtr,
    futureRemainingMomentumPositive: futureSnapshot.volatility.remainingMomentumAtr > 0,
    multipleChange
  };
}

function observationRows(snapshots, config) {
  const byIndex = new Map(snapshots.map((snapshot) => [snapshot.index, snapshot]));
  const selected = snapshots.filter((snapshot) => inWindow(snapshot.date, config));

  return selected.flatMap((snapshot) => {
    const volatility = classifyVolatility(snapshot);
    const shortAtr = classifyShortAtr(snapshot);
    const energy = classifyEnergy(snapshot);
    const trend = classifyTrend(snapshot, config);
    const volume = classifyVolume(snapshot, config);

    return config.horizons.flatMap((horizon) => {
      const futureSnapshot = byIndex.get(snapshot.index + horizon);
      if (!futureSnapshot) return [];
      const future = futureVolatilityStats(snapshot, futureSnapshot);

      return [{
        date: snapshot.date,
        horizon,
        volatilityState: volatility.state,
        shortAtrState: shortAtr.state,
        energyState: energy.state,
        trendState: trend.state,
        volumeState: volume.state,
        atrPct: round(snapshot.volatility.atrPct),
        atrPercentile: round(snapshot.volatility.atrPercentile, 2),
        volatilityMultiple: round(snapshot.volatility.multiple),
        volatilityMultiplePercentile: round(snapshot.volatility.multiplePercentile, 2),
        remainingMomentumAtr: round(snapshot.volatility.remainingMomentumAtr),
        atr3To21: round(snapshot.volatility.fibAtrComparisons.atr3To21),
        atr8To21: round(snapshot.volatility.fibAtrComparisons.atr8To21),
        volumeMultiple: round(snapshot.volume.multiple),
        trendScore: round(snapshot.momentum.trendScore),
        atrChangePct: round(future.atrChangePct),
        atrDirection: future.atrDirection,
        strongAtrUp: future.strongAtrUp ? 1 : 0,
        strongAtrDown: future.strongAtrDown ? 1 : 0,
        futureVolatilityMultiple: round(future.futureVolatilityMultiple),
        futureRemainingMomentumAtr: round(future.futureRemainingMomentumAtr),
        futureRemainingMomentumPositive: future.futureRemainingMomentumPositive ? 1 : 0,
        multipleChange: round(future.multipleChange)
      }];
    });
  });
}

function summarizeComponent(rows, componentKey, componentLabel) {
  const groups = new Map();

  for (const row of rows) {
    const key = `${componentLabel}::${row[componentKey]}::${row.horizon}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(row);
  }

  return Array.from(groups.values()).map((groupRows) => {
    const first = groupRows[0];
    const atrChanges = groupRows.map((row) => row.atrChangePct);
    const upPct = safeDivide(groupRows.filter((row) => row.atrDirection === "up").length, groupRows.length) * 100;
    const downPct = safeDivide(groupRows.filter((row) => row.atrDirection === "down").length, groupRows.length) * 100;
    const edge = Math.abs(upPct - downPct);

    return {
      component: componentLabel,
      state: first[componentKey],
      horizon: first.horizon,
      occurrences: groupRows.length,
      confidence: confidenceLabel(groupRows.length, edge),
      probabilityEdgePct: round(edge, 2),
      atrUpProbabilityPct: round(upPct, 2),
      atrDownProbabilityPct: round(downPct, 2),
      strongAtrUpProbabilityPct: round(safeDivide(groupRows.filter((row) => row.strongAtrUp === 1).length, groupRows.length) * 100, 2),
      strongAtrDownProbabilityPct: round(safeDivide(groupRows.filter((row) => row.strongAtrDown === 1).length, groupRows.length) * 100, 2),
      futureRemainingMomentumPositivePct: round(safeDivide(groupRows.filter((row) => row.futureRemainingMomentumPositive === 1).length, groupRows.length) * 100, 2),
      avgAtrChangePct: round(average(atrChanges)),
      medianAtrChangePct: round(median(atrChanges)),
      avgFutureVolatilityMultiple: round(average(groupRows.map((row) => row.futureVolatilityMultiple))),
      medianFutureRemainingMomentumAtr: round(median(groupRows.map((row) => row.futureRemainingMomentumAtr))),
      lastSeen: groupRows.at(-1)?.date || ""
    };
  });
}

function componentSummaryRows(rows) {
  return [
    ...summarizeComponent(rows, "volatilityState", "波动状态"),
    ...summarizeComponent(rows, "shortAtrState", "短ATR状态"),
    ...summarizeComponent(rows, "energyState", "波动超额状态"),
    ...summarizeComponent(rows, "trendState", "趋势状态"),
    ...summarizeComponent(rows, "volumeState", "量能状态")
  ].sort((left, right) =>
    left.component.localeCompare(right.component, "zh-CN") ||
    left.state.localeCompare(right.state, "zh-CN") ||
    left.horizon - right.horizon
  );
}

function summaryLookup(summaryRows) {
  return new Map(summaryRows.map((row) => [`${row.component}::${row.state}::${row.horizon}`, row]));
}

function currentComponentRows(snapshot, summaryRows, config) {
  const volatility = classifyVolatility(snapshot);
  const shortAtr = classifyShortAtr(snapshot);
  const energy = classifyEnergy(snapshot);
  const trend = classifyTrend(snapshot, config);
  const volume = classifyVolume(snapshot, config);
  const lookup = summaryLookup(summaryRows);
  const components = [
    { component: "波动状态", state: volatility.state, confidencePct: volatility.confidencePct },
    { component: "短ATR状态", state: shortAtr.state, confidencePct: shortAtr.confidencePct },
    { component: "波动超额状态", state: energy.state, confidencePct: energy.confidencePct },
    { component: "趋势状态", state: trend.state, confidencePct: trend.confidencePct },
    { component: "量能状态", state: volume.state, confidencePct: volume.confidencePct }
  ];

  return components.flatMap((component) =>
    config.horizons.map((horizon) => {
      const summary = lookup.get(`${component.component}::${component.state}::${horizon}`);

      return {
        date: snapshot.date,
        close: round(snapshot.price.last, 2),
        component: component.component,
        state: component.state,
        currentConfidencePct: component.confidencePct,
        horizon,
        occurrences: summary?.occurrences || 0,
        historicalConfidence: summary?.confidence || "",
        probabilityEdgePct: summary?.probabilityEdgePct ?? "",
        atrUpProbabilityPct: summary?.atrUpProbabilityPct ?? "",
        atrDownProbabilityPct: summary?.atrDownProbabilityPct ?? "",
        strongAtrUpProbabilityPct: summary?.strongAtrUpProbabilityPct ?? "",
        strongAtrDownProbabilityPct: summary?.strongAtrDownProbabilityPct ?? "",
        futureRemainingMomentumPositivePct: summary?.futureRemainingMomentumPositivePct ?? "",
        avgAtrChangePct: summary?.avgAtrChangePct ?? "",
        medianAtrChangePct: summary?.medianAtrChangePct ?? "",
        avgFutureVolatilityMultiple: summary?.avgFutureVolatilityMultiple ?? "",
        medianFutureRemainingMomentumAtr: summary?.medianFutureRemainingMomentumAtr ?? ""
      };
    })
  );
}

function findCurrentRule(rules, kindKey, horizon) {
  return rules.find((row) => row.kindKey === kindKey && row.horizon === horizon);
}

function findComponent(componentRows, component, horizon) {
  return componentRows.find((row) => row.component === component && row.horizon === horizon);
}

function scoreRouteStrategies(snapshot, config) {
  const labels = buildWeatherLabels(snapshot, config);
  const routeResult = routeStrategies(snapshot, labels);
  const aggregate = routeResult.scores;
  const scores = [
    { key: "trendFollowing", label: "趋势策略天气", score: round(aggregate.trendFollowing, 2) },
    { key: "breakout", label: "突破策略天气", score: round(aggregate.breakout, 2) },
    { key: "meanReversion", label: "均值回归天气", score: round(aggregate.meanReversion, 2) },
    { key: "grid", label: "网格震荡天气", score: round(aggregate.grid, 2) },
    { key: "wait", label: "防守等待", score: round(aggregate.wait, 2) }
  ].sort((left, right) => right.score - left.score);

  return {
    scores,
    topRoute: routeResult.topRoutes[0] ?? scores[0],
    topActiveScore: round(Math.max(
      aggregate.trendFollowing,
      aggregate.breakout,
      aggregate.meanReversion,
      aggregate.grid
    ), 2),
    waitScore: round(aggregate.wait, 2),
    routeResult
  };
}

function gateFromScores(strategyScores, deviationFinal, snapshot, currentComponentRows) {
  const topActive = strategyScores.topActiveScore;
  const wait = strategyScores.waitScore;
  const energy5 = findComponent(currentComponentRows, "波动超额状态", 5);
  const vol5 = findComponent(currentComponentRows, "波动状态", 5);
  const bigWeak = deviationFinal.weather?.includes("大周期弱势") || false;
  const energyLow = energy5?.state === "振幅未满ATR";
  const compressed = vol5?.state === "波动压缩";

  if (bigWeak && energyLow && topActive < 65) return "黄偏红";
  if (wait >= 70 && topActive < 60) return "红";
  if (wait >= 60 && topActive < 65) return "黄偏红";
  if (topActive >= 75 && wait < 50) return "绿";
  if (topActive >= 65 && wait < 60) return "黄偏绿";
  if (compressed && topActive < 60) return "黄";
  if (snapshot.volatility.atrPercentile <= 15 && energyLow) return "黄偏红";
  return "黄";
}

const LIGHT_GREEN = "\u7eff\u706f";
const LIGHT_YELLOW = "\u9ec4\u706f";
const LIGHT_RED = "\u7ea2\u706f";
const GATE_GREEN = "\u7eff";
const GATE_YELLOW_GREEN = "\u9ec4\u504f\u7eff";
const GATE_YELLOW = "\u9ec4";
const GATE_YELLOW_RED = "\u9ec4\u504f\u7ea2";
const GATE_RED = "\u7ea2";
const MIN_CALIBRATION_OCCURRENCES = 30;
const MIN_CALIBRATION_CONFIDENCE_PCT = 40;
const CONFIDENCE_GATE_PASS = "\u6837\u672c\u901a\u8fc7";
const CONFIDENCE_GATE_WEAK = "\u6837\u672c\u4e0d\u8db3";

function routeFamilyFromKey(routeKey = "") {
  if (routeKey.startsWith("trend")) return "trend";
  if (routeKey.startsWith("breakout")) return "breakout";
  if (routeKey.startsWith("meanReversion")) return "meanReversion";
  if (routeKey === "gridNeutral") return "grid";
  if (routeKey === "waitDefense") return "wait";
  return "";
}

function routeDirectionFromKey(routeKey = "") {
  if (routeKey.endsWith("Long") || routeKey.endsWith("Up")) return "long";
  if (routeKey.endsWith("Short") || routeKey.endsWith("Down")) return "short";
  return "neutral";
}

function isWaitSignal(signal) {
  return routeFamilyFromKey(signal?.routeKey || "") === "wait";
}

function lightRank(light) {
  if (light === LIGHT_GREEN) return 3;
  if (light === LIGHT_YELLOW) return 2;
  if (light === LIGHT_RED) return 1;
  return 0;
}

function numeric(value) {
  const next = Number(value);
  return Number.isFinite(next) ? next : 0;
}

function calibrationRowKey(routeKey, horizon) {
  return `${routeKey}::${horizon}`;
}

function calibrationRowsBySignalKey(rows = []) {
  const lookup = new Map();
  for (const row of rows) {
    lookup.set(calibrationRowKey(row.routeKey, row.horizon), row);
  }
  return lookup;
}

function signalOccurrences(signal, rowLookup) {
  const direct = Number(signal?.occurrences);
  if (Number.isFinite(direct)) return direct;
  const row = rowLookup.get(calibrationRowKey(signal?.routeKey, signal?.bestHorizon));
  return numeric(row?.occurrences);
}

function confidenceGateReason(occurrences, confidencePct) {
  if (occurrences < MIN_CALIBRATION_OCCURRENCES && confidencePct < MIN_CALIBRATION_CONFIDENCE_PCT) {
    return `occurrences ${occurrences} < ${MIN_CALIBRATION_OCCURRENCES}, sampleConfidencePct ${round(confidencePct, 2)} < ${MIN_CALIBRATION_CONFIDENCE_PCT}`;
  }
  if (occurrences < MIN_CALIBRATION_OCCURRENCES) {
    return `occurrences ${occurrences} < ${MIN_CALIBRATION_OCCURRENCES}`;
  }
  if (confidencePct < MIN_CALIBRATION_CONFIDENCE_PCT) {
    return `sampleConfidencePct ${round(confidencePct, 2)} < ${MIN_CALIBRATION_CONFIDENCE_PCT}`;
  }
  return "";
}

function applyConfidenceGateToSignal(signal, rowLookup) {
  const occurrences = signalOccurrences(signal, rowLookup);
  const sampleConfidencePct = numeric(signal?.sampleConfidencePct);
  const weakSample = occurrences < MIN_CALIBRATION_OCCURRENCES ||
    sampleConfidencePct < MIN_CALIBRATION_CONFIDENCE_PCT;
  const rawLight = signal.light;
  const light = weakSample && rawLight === LIGHT_GREEN ? LIGHT_YELLOW : rawLight;

  return {
    ...signal,
    occurrences,
    rawLight,
    light,
    confidenceGate: weakSample ? CONFIDENCE_GATE_WEAK : CONFIDENCE_GATE_PASS,
    confidenceGateReason: weakSample ? confidenceGateReason(occurrences, sampleConfidencePct) : ""
  };
}

function applyConfidenceGateToSignals(signals, calibrationRows) {
  const rowLookup = calibrationRowsBySignalKey(calibrationRows);
  return (signals || []).map((signal) => applyConfidenceGateToSignal(signal, rowLookup));
}

function compareCalibratedSignals(left, right) {
  return lightRank(right.light) - lightRank(left.light) ||
    numeric(right.calibrationScore) - numeric(left.calibrationScore) ||
    numeric(right.currentScore) - numeric(left.currentScore);
}

function bestCalibratedSignal(signals) {
  if (!signals?.length) return null;
  return [...signals].sort(compareCalibratedSignals)[0] || null;
}

function routeFromSignal(signal, strategyScores) {
  const rawRoute = strategyScores.routeResult?.routes?.find((route) => route.key === signal.routeKey);
  return {
    ...(rawRoute || {}),
    key: signal.routeKey,
    label: signal.routeLabel || rawRoute?.label || signal.routeKey,
    family: rawRoute?.family || routeFamilyFromKey(signal.routeKey),
    direction: rawRoute?.direction || routeDirectionFromKey(signal.routeKey),
    score: round(numeric(signal.currentScore || rawRoute?.score), 2),
    light: signal.light,
    rawLight: signal.rawLight || signal.light,
    calibrationScore: signal.calibrationScore,
    bestHorizon: signal.bestHorizon,
    sampleConfidencePct: signal.sampleConfidencePct,
    occurrences: signal.occurrences,
    confidenceGate: signal.confidenceGate,
    confidenceGateReason: signal.confidenceGateReason
  };
}

function applyCalibrationToStrategyScores(strategyScores, signals) {
  const topSignal = bestCalibratedSignal(signals);
  if (!topSignal) return { ...strategyScores, calibratedTopSignal: null };

  return {
    ...strategyScores,
    topRoute: routeFromSignal(topSignal, strategyScores),
    calibratedTopSignal: topSignal
  };
}

function gateFromCalibration(signals, strategyScores, deviationFinal, snapshot, currentComponentRows) {
  if (!signals?.length) {
    return gateFromScores(strategyScores, deviationFinal, snapshot, currentComponentRows);
  }

  const waitSignal = signals.find(isWaitSignal);
  const activeSignals = signals.filter((signal) => !isWaitSignal(signal));
  const bestActive = bestCalibratedSignal(activeSignals);
  const greenActive = activeSignals.filter((signal) => signal.light === LIGHT_GREEN);
  const yellowActive = activeSignals.filter((signal) => signal.light === LIGHT_YELLOW);
  const redActive = activeSignals.filter((signal) => signal.light === LIGHT_RED);
  const activeCount = activeSignals.length;
  const allActiveRed = activeCount > 0 && redActive.length >= Math.max(1, activeCount - 1);
  const waitGreen = waitSignal?.light === LIGHT_GREEN;
  const waitYellowStrong = waitSignal?.light === LIGHT_YELLOW &&
    numeric(waitSignal.currentScore) >= 65 &&
    numeric(waitSignal.calibrationScore) >= 55;
  const defensiveDeviation = deviationFinal?.gate === GATE_RED || deviationFinal?.gate === GATE_YELLOW_RED;

  if (!bestActive && waitSignal) {
    if (waitGreen) return GATE_RED;
    if (waitSignal.light === LIGHT_YELLOW) return GATE_YELLOW_RED;
    return GATE_YELLOW;
  }

  if (waitGreen && !greenActive.length) return allActiveRed ? GATE_RED : GATE_YELLOW_RED;
  if (allActiveRed) return waitYellowStrong ? GATE_RED : GATE_YELLOW_RED;

  if (greenActive.length) {
    if (defensiveDeviation || waitGreen || waitYellowStrong || redActive.length >= 3) return GATE_YELLOW_GREEN;
    return GATE_GREEN;
  }

  if (yellowActive.length) {
    if (defensiveDeviation) return GATE_YELLOW_RED;
    if (waitYellowStrong && numeric(waitSignal.currentScore) >= numeric(bestActive?.currentScore)) return GATE_YELLOW;
    if (numeric(bestActive?.calibrationScore) >= 58 && redActive.length <= 3) return GATE_YELLOW_GREEN;
    return GATE_YELLOW;
  }

  if (waitYellowStrong) return GATE_YELLOW_RED;
  return GATE_YELLOW;
}

function actionBias(gate, strategyScores, deviationFinal, currentComponentRows) {
  const top = strategyScores.topRoute;
  const topKey = top?.key || "";
  const topFamily = top?.family || topKey;
  const energy5 = findComponent(currentComponentRows, "波动超额状态", 5);
  const vol5 = findComponent(currentComponentRows, "波动状态", 5);

  if (gate === "红") return "防守等待，策略环境不友好";
  if (gate === "黄偏红") return "谨慎观察，不把单一短期偏离当入场理由";
  if (topFamily === "wait" || topKey === "waitDefense") return "等待更清楚的波动或位置共振";
  if (topFamily === "breakout" && vol5?.state === "波动压缩") return "突破预备天气，等待放量和方向确认";
  if (topFamily === "meanReversion") return "均值回归可观察，但要服从大周期过滤";
  if (topFamily === "grid") return "震荡/网格天气较友好，仍需控制突破风险";
  if (topFamily === "trend") return "趋势天气较友好，等方向和量能确认";
  if (energy5?.state === "振幅未满ATR") return "当根振幅未满ATR，避免追单";
  return deviationFinal.actionBias || "观察";
}

function currentSnapshotRow(snapshot, deviationRules, currentComponentRows, strategyScores, gate) {
  const middle10 = findCurrentRule(deviationRules.currentRuleRows, "middle", 10);
  const ma10 = findCurrentRule(deviationRules.currentRuleRows, "ma233", 10);
  const volatility5 = findComponent(currentComponentRows, "波动状态", 5);
  const shortAtr5 = findComponent(currentComponentRows, "短ATR状态", 5);
  const energy5 = findComponent(currentComponentRows, "波动超额状态", 5);
  const trend = classifyTrend(snapshot, { thresholds: { strongTrendPct: 3, weakTrendPct: 1.2 } });
  const volume = classifyVolume(snapshot, { thresholds: { volumeExpansion: 1.5 } });

  return {
    date: snapshot.date,
    close: round(snapshot.price.last, 2),
    gate,
    topWeatherRoute: strategyScores.topRoute.label,
    topWeatherScore: strategyScores.topRoute.score,
    topWeatherLight: strategyScores.calibratedTopSignal?.light || "",
    topWeatherRawLight: strategyScores.calibratedTopSignal?.rawLight || strategyScores.calibratedTopSignal?.light || "",
    topWeatherCalibrationScore: strategyScores.calibratedTopSignal?.calibrationScore ?? "",
    topWeatherBestHorizon: strategyScores.calibratedTopSignal?.bestHorizon ?? "",
    topWeatherOccurrences: strategyScores.calibratedTopSignal?.occurrences ?? "",
    topWeatherSampleConfidencePct: strategyScores.calibratedTopSignal?.sampleConfidencePct ?? "",
    topWeatherConfidenceGate: strategyScores.calibratedTopSignal?.confidenceGate || "",
    actionBias: actionBias(gate, strategyScores, deviationRules.finalWeather, currentComponentRows),
    volatilityState: volatility5?.state || "",
    atrPct: round(snapshot.volatility.atrPct),
    atrPercentile: round(snapshot.volatility.atrPercentile, 2),
    volatilityMultiple: round(snapshot.volatility.multiple),
    volatilityMultiplePercentile: round(snapshot.volatility.multiplePercentile, 2),
    remainingMomentumAtr: round(snapshot.volatility.remainingMomentumAtr),
    remainingMomentumState: energy5?.state || "",
    shortAtrState: shortAtr5?.state || "",
    atr3Pct: round(snapshot.volatility.fibAtr["3"]?.atrPct),
    atr8Pct: round(snapshot.volatility.fibAtr["8"]?.atrPct),
    atr13Pct: round(snapshot.volatility.fibAtr["13"]?.atrPct),
    atr21Pct: round(snapshot.volatility.fibAtr["21"]?.atrPct),
    atr3To21: round(snapshot.volatility.fibAtrComparisons.atr3To21),
    atr8To21: round(snapshot.volatility.fibAtrComparisons.atr8To21),
    fiveDayAtrDownProbabilityPct: volatility5?.atrDownProbabilityPct ?? "",
    fiveDayAtrUpProbabilityPct: volatility5?.atrUpProbabilityPct ?? "",
    fiveDayFutureMomentumPositivePct: energy5?.futureRemainingMomentumPositivePct ?? "",
    middleState: middle10?.state || "",
    middleDeviationRate: middle10?.deviationRate ?? "",
    middleDeviationAtr: middle10?.deviationAtr ?? "",
    middlePositionPct: round(snapshot.position.middlePositionPct, 2),
    middleTenDayReturnCloserPct: middle10?.returnCloserProbabilityPct ?? "",
    maState: ma10?.state || "",
    maDeviationRate: ma10?.deviationRate ?? "",
    maDeviationAtr: ma10?.deviationAtr ?? "",
    maPositionPct: round(snapshot.position.maPositionPct, 2),
    maTenDayContinueAwayPct: ma10?.continueAwayProbabilityPct ?? "",
    trendState: trend.state,
    trendScore: round(snapshot.momentum.trendScore),
    resonanceDirection: snapshot.momentum.resonanceDirection,
    resonanceCount: snapshot.momentum.resonanceCount,
    volumeState: volume.state,
    volumeMultiple: round(snapshot.volume.multiple),
    weatherSummary: `${volatility5?.state || "未知波动"} / ${energy5?.state || "未知动能"} / ${middle10?.weatherTag || ""} / ${ma10?.weatherTag || ""}`
  };
}

export function buildMarketWeatherRouter(cleanPayload, config) {
  const snapshots = buildIndicatorSnapshots(cleanPayload.candles, config);
  const selected = snapshots.filter((snapshot) => inWindow(snapshot.date, config));
  const latest = selected.at(-1);
  const volatilityObservationRows = observationRows(snapshots, config);
  const summaryRows = componentSummaryRows(volatilityObservationRows);
  const deviationStudy = runDeviationStudyFromSnapshots(cleanPayload, config, snapshots);
  const deviationRules = buildDeviationRules(deviationStudy);
  const componentRows = latest ? currentComponentRows(latest, summaryRows, config) : [];
  const calibration = latest ? runRouterCalibration(cleanPayload, config, snapshots) : null;
  const calibrationSignals = applyConfidenceGateToSignals(
    calibration?.metadata?.currentSignals || [],
    calibration?.calibrationRows || []
  );
  const rawStrategyScores = latest ? scoreRouteStrategies(latest, config) : { scores: [], topActiveScore: 0, waitScore: 0, topRoute: null };
  const strategyScores = latest ? applyCalibrationToStrategyScores(rawStrategyScores, calibrationSignals) : rawStrategyScores;
  const gate = latest ? gateFromCalibration(calibrationSignals, strategyScores, deviationRules.finalWeather, latest, componentRows) : "数据不足";
  const current = latest ? currentSnapshotRow(latest, deviationRules, componentRows, strategyScores, gate) : null;

  return {
    metadata: {
      instrument: cleanPayload.metadata.instrument,
      bar: cleanPayload.metadata.bar,
      fromDate: config.fromDate,
      toDate: config.toDate,
      firstDate: selected[0]?.date || null,
      lastDate: latest?.date || null,
      snapshotCount: selected.length,
      observationRows: volatilityObservationRows.length,
      routerCalibrationRows: calibration?.calibrationRows?.length || 0,
      routerCalibrationObservationRows: calibration?.metadata?.observationRows || 0,
      gateSource: calibrationSignals.length ? "router_calibration" : "score_fallback",
      calibrationConfidenceGate: {
        minOccurrences: MIN_CALIBRATION_OCCURRENCES,
        minSampleConfidencePct: MIN_CALIBRATION_CONFIDENCE_PCT,
        effect: "green_signals_below_threshold_are_downgraded_to_yellow"
      },
      currentCalibrationSignals: calibrationSignals,
      horizons: config.horizons,
      generatedAt: new Date().toISOString(),
      routerPrinciple: "ATR/振幅/波动超额负责波动天气，中值乖离负责短期拉伸，233MA乖离负责大周期过滤。输出是策略适配天气，不是买卖信号。"
    },
    current,
    strategyScores: strategyScores.scores,
    deviationFinalWeather: deviationRules.finalWeather,
    currentComponentRows: componentRows,
    componentSummaryRows: summaryRows,
    observationRows: volatilityObservationRows
  };
}
