import { buildIndicatorSnapshots } from "./indicators.mjs";
import { runDeviationStudyFromSnapshots } from "./deviation-study.mjs";
import { buildDeviationRules } from "./deviation-rules.mjs";

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

function scoreStrategies(snapshot, deviationRules, currentComponentRows) {
  const middle10 = findCurrentRule(deviationRules.currentRuleRows, "middle", 10);
  const ma10 = findCurrentRule(deviationRules.currentRuleRows, "ma233", 10);
  const vol5 = findComponent(currentComponentRows, "波动状态", 5);
  const shortAtr5 = findComponent(currentComponentRows, "短ATR状态", 5);
  const energy5 = findComponent(currentComponentRows, "波动超额状态", 5);
  const trend = classifyTrend(snapshot, { thresholds: { strongTrendPct: 3, weakTrendPct: 1.2 } });
  const absTrend = Math.abs(snapshot.momentum.trendScore);
  const strongTrend = trend.strength === "strong";
  const bigWeak = ma10?.state.includes("下侧") || false;
  const bigExtreme = ma10?.state.includes("极端") || false;
  const middleExtreme = middle10?.state.includes("极端") || false;
  const middleDeviation = middle10?.state.includes("偏离") || false;
  const compressed = vol5?.state === "波动压缩";
  const lowStart = vol5?.state === "低波动启动";
  const highExpansion = vol5?.state === "高波动扩张";
  const shortHeating = shortAtr5?.state === "短ATR升温";
  const shortCooling = shortAtr5?.state === "短ATR降温";
  const energyLow = energy5?.state === "振幅未满ATR";
  const energyPositive = energy5?.state === "振幅已超ATR";
  const volumeMultiple = snapshot.volume.multiple;
  const atrPercentile = snapshot.volatility.atrPercentile;
  const volatilityMultiple = snapshot.volatility.multiple;
  const middleCloserEdge = (Number(middle10?.returnCloserProbabilityPct) || 0) - (Number(middle10?.continueAwayProbabilityPct) || 0);

  const trendScore = clamp(
    18 + (strongTrend ? 32 : 0) + Math.min(absTrend * 6, 30) + (volumeMultiple >= 1.15 ? 8 : 0) -
      (compressed ? 18 : 0) - (energyLow ? 10 : 0) - (bigWeak ? 10 : 0),
    0,
    100
  );
  const breakoutScore = clamp(
    16 + (compressed ? 22 : 0) + (lowStart ? 18 : 0) + (shortHeating ? 28 : 0) +
      (volumeMultiple >= 1.2 ? 12 : 0) + (energyPositive ? 10 : 0) -
      (shortCooling ? 18 : 0) - (energyLow ? 12 : 0),
    0,
    100
  );
  const meanReversionScore = clamp(
    18 + (middleExtreme ? 42 : 0) + (middleDeviation ? 18 : 0) +
      clamp(middleCloserEdge * 1.8, -18, 24) + (shortCooling ? 8 : 0) -
      (highExpansion ? 12 : 0) - (bigWeak && !middleExtreme ? 14 : 0),
    0,
    100
  );
  const gridScore = clamp(
    34 + (atrPercentile <= 40 ? 16 : 0) + (volatilityMultiple <= 1 ? 16 : 0) +
      (absTrend < 1.2 ? 18 : 0) + (volumeMultiple >= 0.75 && volumeMultiple <= 1.2 ? 8 : 0) -
      (highExpansion ? 30 : 0) - (middleExtreme ? 20 : 0) - (bigExtreme ? 10 : 0),
    0,
    100
  );
  const topActive = Math.max(trendScore, breakoutScore, meanReversionScore, gridScore);
  const waitScore = clamp(
    25 + (bigWeak ? 20 : 0) + (energyLow ? 16 : 0) + (shortCooling ? 10 : 0) +
      (compressed && !shortHeating ? 12 : 0) + (topActive < 55 ? 18 : 0) - (topActive * 0.12),
    0,
    100
  );
  const scores = [
    { key: "trend", label: "趋势策略天气", score: round(trendScore, 2) },
    { key: "breakout", label: "突破策略天气", score: round(breakoutScore, 2) },
    { key: "meanReversion", label: "均值回归天气", score: round(meanReversionScore, 2) },
    { key: "grid", label: "网格震荡天气", score: round(gridScore, 2) },
    { key: "wait", label: "防守等待", score: round(waitScore, 2) }
  ].sort((left, right) => right.score - left.score);

  return {
    scores,
    topRoute: scores[0],
    topActiveScore: round(topActive, 2),
    waitScore: round(waitScore, 2)
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

function actionBias(gate, strategyScores, deviationFinal, currentComponentRows) {
  const top = strategyScores.topRoute;
  const energy5 = findComponent(currentComponentRows, "波动超额状态", 5);
  const vol5 = findComponent(currentComponentRows, "波动状态", 5);

  if (gate === "红") return "防守等待，策略环境不友好";
  if (gate === "黄偏红") return "谨慎观察，不把单一短期偏离当入场理由";
  if (top.key === "wait") return "等待更清楚的波动或位置共振";
  if (top.key === "breakout" && vol5?.state === "波动压缩") return "突破预备天气，等待放量和方向确认";
  if (top.key === "meanReversion") return "均值回归可观察，但要服从大周期过滤";
  if (top.key === "grid") return "震荡/网格天气较友好，仍需控制突破风险";
  if (top.key === "trend") return "趋势天气较友好，等方向和量能确认";
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
  const strategyScores = latest ? scoreStrategies(latest, deviationRules, componentRows) : { scores: [], topActiveScore: 0, waitScore: 0, topRoute: null };
  const gate = latest ? gateFromScores(strategyScores, deviationRules.finalWeather, latest, componentRows) : "数据不足";
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
