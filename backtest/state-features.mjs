export const stateFeatureDefs = [
  { key: "rangePct", label: "振幅率", pick: (s) => s.volatility.rangePct },
  { key: "atrPct", label: "ATR率", pick: (s) => s.volatility.atrPct },
  { key: "atrPercentile", label: "ATR百分位", pick: (s) => s.volatility.atrPercentile },
  { key: "volatilityMultiple", label: "波动倍率", pick: (s) => s.volatility.multiple },
  { key: "volatilityMultiplePercentile", label: "波动倍率百分位", pick: (s) => s.volatility.multiplePercentile },
  { key: "volatilityExcess", label: "波动超额", pick: (s) => s.volatility.excess },
  { key: "remainingMomentumPct", label: "剩余动能率", pick: (s) => s.volatility.remainingMomentumPct },
  { key: "remainingMomentumAtr", label: "剩余动能ATR", pick: (s) => s.volatility.remainingMomentumAtr },
  { key: "atr3Pct", label: "3日ATR率", pick: (s) => s.volatility.fibAtr["3"].atrPct },
  { key: "atr8Pct", label: "8日ATR率", pick: (s) => s.volatility.fibAtr["8"].atrPct },
  { key: "atr13Pct", label: "13日ATR率", pick: (s) => s.volatility.fibAtr["13"].atrPct },
  { key: "atr21Pct", label: "21日ATR率", pick: (s) => s.volatility.fibAtr["21"].atrPct },
  { key: "atr3Percentile", label: "3日ATR百分位", pick: (s) => s.volatility.fibAtr["3"].atrPercentile },
  { key: "atr8Percentile", label: "8日ATR百分位", pick: (s) => s.volatility.fibAtr["8"].atrPercentile },
  { key: "atr13Percentile", label: "13日ATR百分位", pick: (s) => s.volatility.fibAtr["13"].atrPercentile },
  { key: "atr21Percentile", label: "21日ATR百分位", pick: (s) => s.volatility.fibAtr["21"].atrPercentile },
  { key: "volatilityMultiple3", label: "振幅/3日ATR", pick: (s) => s.volatility.fibAtr["3"].multiple },
  { key: "volatilityMultiple8", label: "振幅/8日ATR", pick: (s) => s.volatility.fibAtr["8"].multiple },
  { key: "volatilityMultiple13", label: "振幅/13日ATR", pick: (s) => s.volatility.fibAtr["13"].multiple },
  { key: "volatilityMultiple21", label: "振幅/21日ATR", pick: (s) => s.volatility.fibAtr["21"].multiple },
  { key: "volatilityMultiple3Percentile", label: "振幅/3日ATR百分位", pick: (s) => s.volatility.fibAtr["3"].multiplePercentile },
  { key: "volatilityMultiple8Percentile", label: "振幅/8日ATR百分位", pick: (s) => s.volatility.fibAtr["8"].multiplePercentile },
  { key: "volatilityMultiple13Percentile", label: "振幅/13日ATR百分位", pick: (s) => s.volatility.fibAtr["13"].multiplePercentile },
  { key: "volatilityMultiple21Percentile", label: "振幅/21日ATR百分位", pick: (s) => s.volatility.fibAtr["21"].multiplePercentile },
  { key: "remainingMomentumAtr3", label: "3日剩余动能ATR", pick: (s) => s.volatility.fibAtr["3"].remainingMomentumAtr },
  { key: "remainingMomentumAtr8", label: "8日剩余动能ATR", pick: (s) => s.volatility.fibAtr["8"].remainingMomentumAtr },
  { key: "remainingMomentumAtr13", label: "13日剩余动能ATR", pick: (s) => s.volatility.fibAtr["13"].remainingMomentumAtr },
  { key: "remainingMomentumAtr21", label: "21日剩余动能ATR", pick: (s) => s.volatility.fibAtr["21"].remainingMomentumAtr },
  { key: "atr3To21", label: "3/21日ATR比", pick: (s) => s.volatility.fibAtrComparisons.atr3To21 },
  { key: "atr8To21", label: "8/21日ATR比", pick: (s) => s.volatility.fibAtrComparisons.atr8To21 },
  { key: "atr13To21", label: "13/21日ATR比", pick: (s) => s.volatility.fibAtrComparisons.atr13To21 },
  { key: "atr3To8", label: "3/8日ATR比", pick: (s) => s.volatility.fibAtrComparisons.atr3To8 },
  { key: "atr8To13", label: "8/13日ATR比", pick: (s) => s.volatility.fibAtrComparisons.atr8To13 },
  { key: "volumeMultiple", label: "量能倍率", pick: (s) => s.volume.multiple },
  { key: "d8", label: "8日涨跌", pick: (s) => s.momentum.d8 },
  { key: "d13", label: "13日涨跌", pick: (s) => s.momentum.d13 },
  { key: "d21", label: "21日涨跌", pick: (s) => s.momentum.d21 },
  { key: "d34", label: "34日涨跌", pick: (s) => s.momentum.d34 },
  { key: "trendScore", label: "趋势动能", pick: (s) => s.momentum.trendScore },
  { key: "resonanceCount", label: "共振数量", pick: (s) => s.momentum.resonanceCount },
  { key: "middleDeviationRate", label: "中值乖离率", pick: (s) => s.position.middleDeviationRate },
  { key: "middleDeviationAtr", label: "中值乖离ATR", pick: (s) => s.position.middleDeviationAtr },
  { key: "middlePositionPct", label: "中值位置百分位", pick: (s) => s.position.middlePositionPct },
  { key: "maDeviationRate", label: "233MA乖离率", pick: (s) => s.position.maDeviationRate },
  { key: "maDeviationAtr", label: "233MA乖离ATR", pick: (s) => s.position.maDeviationAtr },
  { key: "maPositionPct", label: "MA位置百分位", pick: (s) => s.position.maPositionPct },
  { key: "stretchHeat", label: "拉伸热度", pick: (s) => s.position.stretchHeat }
];

function finite(value) {
  return Number.isFinite(value);
}

function average(values) {
  if (!values.length) return 0;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function stddev(values, mean) {
  if (values.length < 2) return 1;
  const variance = average(values.map((value) => (value - mean) ** 2));
  return Math.sqrt(variance) || 1;
}

function clamp(value, min, max) {
  if (!finite(value)) return 0;
  return Math.min(max, Math.max(min, value));
}

export function buildFeatureDataset(snapshots) {
  const rawRows = snapshots.map((snapshot) => {
    const values = Object.fromEntries(stateFeatureDefs.map((feature) => [
      feature.key,
      feature.pick(snapshot)
    ]));

    return {
      date: snapshot.date,
      index: snapshot.index,
      close: snapshot.price.last,
      values,
      snapshot
    };
  }).filter((row) => Object.values(row.values).every(finite));

  const stats = Object.fromEntries(stateFeatureDefs.map((feature) => {
    const values = rawRows.map((row) => row.values[feature.key]);
    const mean = average(values);
    return [
      feature.key,
      {
        key: feature.key,
        label: feature.label,
        mean,
        std: stddev(values, mean),
        min: Math.min(...values),
        max: Math.max(...values)
      }
    ];
  }));

  const rows = rawRows.map((row) => ({
    ...row,
    vector: stateFeatureDefs.map((feature) => {
      const featureStats = stats[feature.key];
      return clamp((row.values[feature.key] - featureStats.mean) / featureStats.std, -5, 5);
    })
  }));

  return {
    features: stateFeatureDefs.map(({ key, label }) => ({ key, label })),
    stats,
    rows
  };
}

export function meanFeatureValues(rows) {
  return Object.fromEntries(stateFeatureDefs.map((feature) => [
    feature.key,
    average(rows.map((row) => row.values[feature.key]))
  ]));
}

export function zProfile(values, stats) {
  return Object.fromEntries(stateFeatureDefs.map((feature) => [
    feature.key,
    (values[feature.key] - stats[feature.key].mean) / stats[feature.key].std
  ]));
}

export function strongestFeatures(zValues, limit = 5) {
  return stateFeatureDefs
    .map((feature) => ({
      key: feature.key,
      label: feature.label,
      z: zValues[feature.key]
    }))
    .sort((left, right) => Math.abs(right.z) - Math.abs(left.z))
    .slice(0, limit);
}
