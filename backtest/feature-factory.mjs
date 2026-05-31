import { buildIndicatorSnapshots } from "./indicators.mjs";
import { routeStrategies } from "./strategy-router.mjs";
import { buildFeatureDataset } from "./state-features.mjs";
import { classifyVolatilityState } from "./volatility-state.mjs";

function finite(value) {
  return Number.isFinite(value);
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

function inWindow(date, config) {
  if (config.fromDate && date < config.fromDate) return false;
  if (config.toDate && date > config.toDate) return false;
  return true;
}

function labelTone(label) {
  if (label.includes("下行")) return "negative";
  if (label.includes("上行")) return "positive";
  if (label.includes("下侧") || label.includes("冷却") || label.includes("压缩") || label.includes("弱势")) return "warning";
  if (label.includes("上侧") || label.includes("扩张") || label.includes("强趋势") || label.includes("放量")) return "positive";
  return "neutral";
}

export function classifyPositionDeviation(deviationAtr, positionPct, prefix) {
  const absDeviation = Math.abs(deviationAtr);

  if (absDeviation <= 0.35) {
    return {
      label: `${prefix}贴近`,
      side: 0,
      extremity: "near",
      confidence: clamp(1 - (absDeviation / 0.35), 0, 1)
    };
  }

  if (deviationAtr > 0) {
    const extreme = positionPct >= 85 || absDeviation >= 2.5;
    return {
      label: extreme ? `${prefix}上侧极端` : `${prefix}上侧偏离`,
      side: 1,
      extremity: extreme ? "extreme" : "deviation",
      confidence: extreme ? clamp(Math.max((positionPct - 70) / 30, absDeviation / 4), 0, 1) : clamp(absDeviation / 2, 0, 1)
    };
  }

  const extreme = positionPct <= 15 || absDeviation >= 2.5;
  return {
    label: extreme ? `${prefix}下侧极端` : `${prefix}下侧偏离`,
    side: -1,
    extremity: extreme ? "extreme" : "deviation",
    confidence: extreme ? clamp(Math.max((30 - positionPct) / 30, absDeviation / 4), 0, 1) : clamp(absDeviation / 2, 0, 1)
  };
}

function classifyTrend(snapshot, thresholds) {
  const { resonanceDirection, resonanceCount, trendScore } = snapshot.momentum;
  const absTrend = Math.abs(trendScore);

  if (resonanceCount >= 3 && absTrend >= thresholds.strongTrendPct && resonanceDirection !== "mixed") {
    return {
      label: resonanceDirection === "up" ? "强趋势上行" : "强趋势下行",
      direction: resonanceDirection,
      strength: "strong",
      confidence: clamp((absTrend / (thresholds.strongTrendPct * 2)) + (resonanceCount / 8), 0, 1)
    };
  }

  if (resonanceCount >= 2 && absTrend >= thresholds.weakTrendPct) {
    return {
      label: resonanceDirection === "up" ? "弱趋势上行" : resonanceDirection === "down" ? "弱趋势下行" : "弱趋势混合",
      direction: resonanceDirection,
      strength: "weak",
      confidence: clamp((absTrend / (thresholds.strongTrendPct * 2)) + (resonanceCount / 10), 0, 0.75)
    };
  }

  return {
    label: "趋势不明",
    direction: "mixed",
    strength: "none",
    confidence: clamp(1 - (absTrend / thresholds.strongTrendPct), 0, 1)
  };
}

function classifyVolume(snapshot, thresholds) {
  const multiple = snapshot.volume.multiple;

  if (multiple >= thresholds.volumeExpansion) {
    return {
      label: "放量",
      confidence: clamp((multiple - thresholds.volumeExpansion) / thresholds.volumeExpansion, 0.35, 1)
    };
  }

  if (multiple <= 0.75) {
    return {
      label: "缩量",
      confidence: clamp((0.75 - multiple) / 0.75, 0.25, 1)
    };
  }

  return {
    label: "量能正常",
    confidence: clamp(1 - Math.abs(multiple - 1), 0, 1)
  };
}

function classifyEnergy(snapshot) {
  const remaining = snapshot.volatility.remainingMomentumAtr;

  if (remaining >= 0.2) {
    return {
      label: "剩余动能为正",
      confidence: clamp(remaining / 1.2, 0.25, 1)
    };
  }

  if (remaining <= -0.2) {
    return {
      label: "剩余动能不足",
      confidence: clamp(Math.abs(remaining) / 1.2, 0.25, 1)
    };
  }

  return {
    label: "接近正常动能",
    confidence: clamp(1 - Math.abs(remaining) / 0.2, 0, 1)
  };
}

function classifyAtrSlope(snapshot) {
  const { atr3To21, atr8To21 } = snapshot.volatility.fibAtrComparisons;

  if (atr3To21 >= 1.08 && atr8To21 >= 1) {
    return {
      label: "短波动升温",
      confidence: clamp(((atr3To21 - 1) + Math.max(0, atr8To21 - 1)) / 0.35, 0.25, 1)
    };
  }

  if (atr3To21 <= 0.88 && atr8To21 <= 0.96) {
    return {
      label: "短波动降温",
      confidence: clamp(((1 - atr3To21) + Math.max(0, 1 - atr8To21)) / 0.35, 0.25, 1)
    };
  }

  return {
    label: "短波动中性",
    confidence: clamp(1 - Math.abs(atr3To21 - 1), 0, 1)
  };
}

export function buildWeatherLabels(snapshot, config) {
  const volatility = classifyVolatilityState(snapshot);
  const middle = classifyPositionDeviation(
    snapshot.position.middleDeviationAtr,
    snapshot.position.middlePositionPct,
    "中值"
  );
  const ma = classifyPositionDeviation(
    snapshot.position.maDeviationAtr,
    snapshot.position.maPositionPct,
    "MA"
  );
  const trend = classifyTrend(snapshot, config.thresholds);
  const volume = classifyVolume(snapshot, config.thresholds);
  const energy = classifyEnergy(snapshot);
  const atrSlope = classifyAtrSlope(snapshot);

  return [
    { dimension: "波动", label: volatility.state, confidence: volatility.confidence, tone: labelTone(volatility.state) },
    { dimension: "短波动", label: atrSlope.label, confidence: atrSlope.confidence, tone: labelTone(atrSlope.label) },
    { dimension: "中值位置", label: middle.label, confidence: middle.confidence, tone: labelTone(middle.label), side: middle.side, extremity: middle.extremity },
    { dimension: "MA位置", label: ma.label, confidence: ma.confidence, tone: labelTone(ma.label), side: ma.side, extremity: ma.extremity },
    { dimension: "趋势", label: trend.label, confidence: trend.confidence, tone: labelTone(trend.label), direction: trend.direction, strength: trend.strength },
    { dimension: "量能", label: volume.label, confidence: volume.confidence, tone: labelTone(volume.label) },
    { dimension: "动能", label: energy.label, confidence: energy.confidence, tone: labelTone(energy.label) }
  ];
}

function labelByDimension(labels, dimension) {
  return labels.find((label) => label.dimension === dimension);
}

function weatherName(labels) {
  const volatility = labelByDimension(labels, "波动")?.label || "未知波动";
  const trend = labelByDimension(labels, "趋势")?.label || "趋势未知";
  const middle = labelByDimension(labels, "中值位置")?.label || "中值未知";
  const ma = labelByDimension(labels, "MA位置")?.label || "MA未知";
  return `${volatility} / ${trend} / ${middle} / ${ma}`;
}

export function scoreStrategyFit(snapshot, labels) {
  const { thresholds } = snapshot.config || {};
  const strongTrendPct = thresholds?.strongTrendPct || 3;
  const absTrend = Math.abs(snapshot.momentum.trendScore);
  const resonance = snapshot.momentum.resonanceCount;
  const volumeMultiple = snapshot.volume.multiple;
  const atrPercentile = snapshot.volatility.atrPercentile;
  const multiplePercentile = snapshot.volatility.multiplePercentile;
  const volatilityMultiple = snapshot.volatility.multiple;
  const shortHeating = snapshot.volatility.fibAtrComparisons.atr3To21 >= 1.08 && snapshot.volatility.fibAtrComparisons.atr8To21 >= 1;
  const shortCooling = snapshot.volatility.fibAtrComparisons.atr3To21 <= 0.88 && snapshot.volatility.fibAtrComparisons.atr8To21 <= 0.96;
  const volatilityLabel = labelByDimension(labels, "波动")?.label || "";
  const middleLabel = labelByDimension(labels, "中值位置")?.label || "";
  const maLabel = labelByDimension(labels, "MA位置")?.label || "";
  const middleExtreme = middleLabel.includes("极端");
  const maExtreme = maLabel.includes("极端");
  const strongTrend = resonance >= 3 && absTrend >= strongTrendPct;
  const lowTrend = absTrend < 1.2;
  const compressed = volatilityLabel === "波动压缩";
  const highExpansion = volatilityLabel === "高波动扩张";
  const highCooling = volatilityLabel === "高波动冷却";

  const trendFollowing = clamp(
    18 + (resonance * 11) + Math.min(absTrend * 5, 30) + (volumeMultiple >= 1.15 ? 8 : 0) +
      (shortHeating ? 10 : 0) - (compressed ? 14 : 0) - (middleExtreme ? 8 : 0),
    0,
    100
  );

  const breakout = clamp(
    22 + (compressed ? 18 : 0) + (multiplePercentile >= 70 ? 22 : 0) + (shortHeating ? 18 : 0) +
      (volumeMultiple >= 1.2 ? 10 : 0) - (highCooling ? 18 : 0) - (shortCooling ? 8 : 0),
    0,
    100
  );

  const meanReversion = clamp(
    18 + clamp((Math.abs(snapshot.position.middleDeviationAtr) - 0.8) * 18, 0, 35) +
      (middleExtreme ? 24 : 0) + (maExtreme ? 8 : 0) - (strongTrend ? 16 : 0) - (highExpansion ? 8 : 0),
    0,
    100
  );

  const grid = clamp(
    42 + (atrPercentile <= 40 ? 16 : 0) + (volatilityMultiple <= 1 ? 14 : 0) + (lowTrend ? 18 : 0) +
      (volumeMultiple <= 1.15 ? 8 : 0) - (highExpansion ? 30 : 0) -
      (Math.abs(snapshot.position.middleDeviationAtr) >= 1.7 ? 12 : 0) - (volumeMultiple >= 1.5 ? 10 : 0),
    0,
    100
  );

  const maxActiveScore = Math.max(trendFollowing, breakout, meanReversion, grid);
  const cautionBoost = (maExtreme && compressed ? 16 : 0) + (highCooling ? 12 : 0) + (shortCooling ? 8 : 0);
  const wait = clamp(35 + cautionBoost + (maxActiveScore < 45 ? 18 : 0) - (maxActiveScore * 0.22), 0, 100);

  return {
    trendFollowing: round(trendFollowing, 2),
    breakout: round(breakout, 2),
    meanReversion: round(meanReversion, 2),
    grid: round(grid, 2),
    wait: round(wait, 2)
  };
}

function attachConfig(snapshot, config) {
  return {
    ...snapshot,
    config
  };
}

function featureCsvRow(row, labels, strategyScores) {
  const snapshot = row.snapshot;

  return {
    date: snapshot.date,
    close: round(snapshot.price.last, 2),
    weatherName: weatherName(labels),
    weatherConfidencePct: round(average(labels.map((label) => label.confidence)) * 100, 2),
    weatherLabels: labels.map((label) => `${label.dimension}:${label.label}`).join(" | "),
    topRoutes: row.routeResult?.topRoutes.map((item) => `${item.label}:${item.score}`).join(" | ") || "",
    trendLongScore: strategyScores.trendLong,
    trendShortScore: strategyScores.trendShort,
    breakoutUpScore: strategyScores.breakoutUp,
    breakoutDownScore: strategyScores.breakoutDown,
    meanReversionLongScore: strategyScores.meanReversionLong,
    meanReversionShortScore: strategyScores.meanReversionShort,
    gridNeutralScore: strategyScores.gridNeutral,
    waitDefenseScore: strategyScores.waitDefense,
    trendFollowingScore: strategyScores.trendFollowing,
    breakoutScore: strategyScores.breakout,
    meanReversionScore: strategyScores.meanReversion,
    gridScore: strategyScores.grid,
    waitScore: strategyScores.wait,
    changePct: round(snapshot.price.changePct),
    rangePct: round(snapshot.volatility.rangePct),
    atrPct: round(snapshot.volatility.atrPct),
    atrPercentile: round(snapshot.volatility.atrPercentile, 2),
    volatilityMultiple: round(snapshot.volatility.multiple),
    volatilityMultiplePercentile: round(snapshot.volatility.multiplePercentile, 2),
    remainingMomentumAtr: round(snapshot.volatility.remainingMomentumAtr),
    atr3Pct: round(snapshot.volatility.fibAtr["3"].atrPct),
    atr8Pct: round(snapshot.volatility.fibAtr["8"].atrPct),
    atr13Pct: round(snapshot.volatility.fibAtr["13"].atrPct),
    atr21Pct: round(snapshot.volatility.fibAtr["21"].atrPct),
    atr3To21: round(snapshot.volatility.fibAtrComparisons.atr3To21),
    atr8To21: round(snapshot.volatility.fibAtrComparisons.atr8To21),
    volumeMultiple: round(snapshot.volume.multiple),
    d8: round(snapshot.momentum.d8),
    d13: round(snapshot.momentum.d13),
    d21: round(snapshot.momentum.d21),
    d34: round(snapshot.momentum.d34),
    trendScore: round(snapshot.momentum.trendScore),
    resonanceDirection: snapshot.momentum.resonanceDirection,
    resonanceCount: snapshot.momentum.resonanceCount,
    middleDeviationRate: round(snapshot.position.middleDeviationRate),
    middleDeviationAtr: round(snapshot.position.middleDeviationAtr),
    middlePositionPct: round(snapshot.position.middlePositionPct, 2),
    maDeviationRate: round(snapshot.position.maDeviationRate),
    maDeviationAtr: round(snapshot.position.maDeviationAtr),
    maPositionPct: round(snapshot.position.maPositionPct, 2),
    stretchHeat: round(snapshot.position.stretchHeat, 2)
  };
}

export function buildFeatureFactoryDataset(cleanPayload, config) {
  const snapshots = buildIndicatorSnapshots(cleanPayload.candles, config)
    .filter((snapshot) => inWindow(snapshot.date, config));
  const dataset = buildFeatureDataset(snapshots);

  return {
    snapshots,
    dataset
  };
}

export function buildFeatureFactory(cleanPayload, config) {
  const { snapshots, dataset } = buildFeatureFactoryDataset(cleanPayload, config);
  const featureRows = dataset.rows.map((row) => {
    const snapshot = attachConfig(row.snapshot, config);
    const labels = buildWeatherLabels(snapshot, config);
    const routeResult = routeStrategies(snapshot, labels);
    const strategyScores = routeResult.scores;

    return {
      row,
      labels,
      strategyScores,
      routeResult,
      csv: featureCsvRow({ ...row, snapshot, routeResult }, labels, strategyScores)
    };
  });
  const latest = featureRows.at(-1);

  return {
    metadata: {
      instrument: cleanPayload.metadata.instrument,
      bar: cleanPayload.metadata.bar,
      fromDate: config.fromDate,
      toDate: config.toDate,
      firstDate: snapshots[0]?.date || null,
      lastDate: snapshots.at(-1)?.date || null,
      snapshotCount: snapshots.length,
      featureCount: dataset.features.length,
      generatedAt: new Date().toISOString()
    },
    features: dataset.features,
    featureStats: dataset.stats,
    current: latest ? {
      date: latest.row.snapshot.date,
      close: round(latest.row.snapshot.price.last, 2),
      weatherName: weatherName(latest.labels),
      weatherConfidencePct: round(average(latest.labels.map((label) => label.confidence)) * 100, 2),
      labels: latest.labels.map((label) => ({
        ...label,
        confidencePct: round(label.confidence * 100, 2)
      })),
      strategyScores: latest.strategyScores,
      topRoutes: latest.routeResult.topRoutes,
      strategyRoutes: latest.routeResult.routes,
      values: Object.fromEntries(Object.entries(latest.row.values).map(([key, value]) => [key, round(value)]))
    } : null,
    featureRows: featureRows.map((row) => row.csv)
  };
}
